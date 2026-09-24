import base64
import re
import time
from pathlib import Path

import requests
from flask import current_app
from google import genai
from google.genai import types
from PIL import Image


class ImageGenerationError(RuntimeError):
    def __init__(self, message, provider='unknown', status=None):
        super().__init__(message)
        self.provider = provider
        self.status = status


class ImageRateLimitError(ImageGenerationError):
    def __init__(self, message, provider='unknown', status=429, retry_after=None):
        super().__init__(message, provider, status)
        self.retry_after = retry_after


def _retry_delay_from_error(error):
    text = str(error)
    patterns = (
        r'retryDelay["\'\s:=]+["\']?(\d+(?:\.\d+)?)s',
        r'retry in\s+(\d+(?:\.\d+)?)s',
        r'"seconds"\s*:\s*"?(\d+(?:\.\d+)?)',
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return max(0.0, float(match.group(1)))
    return None


def _provider_error(provider, error, status=None, response_text=''):
    raw_error = str(error).strip() or 'The image provider returned an unknown error.'
    key = current_app.config.get('IMAGE_API_KEY') or ''
    raw_error = raw_error.replace(key, '[REDACTED]') if key else raw_error
    message = raw_error
    if status in (401, 403):
        message = 'The image provider rejected the API key.'
    elif status == 404:
        message = 'The configured image model or API endpoint was not found.'
    elif status == 429:
        message = 'The image provider quota is exhausted or unavailable for this account.'
    safe_response = response_text.replace('\n', ' ').replace(key, '[REDACTED]')[:800] if key else response_text.replace('\n', ' ')[:800]
    current_app.logger.error(
        'IMAGE GENERATION ERROR: Provider: %s | HTTP Status: %s | Error: %s | Response: %s',
        provider, status or 'n/a', raw_error, safe_response or 'n/a',
    )
    error_text = f'{raw_error} {response_text}'
    rate_limited = status == 429 or any(term in error_text.lower() for term in ('resource_exhausted', 'rate limit', 'rate_limit', 'quota'))
    if rate_limited:
        return ImageRateLimitError(message, provider, status or 429, _retry_delay_from_error(error_text))
    return ImageGenerationError(message, provider, status)


def validate_generated_image(path):
    path = Path(path)
    if not path.exists() or path.stat().st_size == 0:
        raise ImageGenerationError('The image provider returned an empty image.', 'Google Gemini')
    try:
        with Image.open(path) as image:
            image.verify()
    except Exception as error:
        raise ImageGenerationError('The image provider returned an invalid image.', 'Google Gemini') from error


def _write_provider_response(response, out, provider):
    content_type = response.headers.get('content-type', '').lower()
    if content_type.startswith('image/'):
        out.write_bytes(response.content)
        validate_generated_image(out)
        return
    try:
        payload = response.json()
    except ValueError as error:
        raise _provider_error(provider, 'The provider returned a non-image response.', response.status_code, response.text) from error
    candidates = payload.get('data') if isinstance(payload, dict) else None
    if isinstance(candidates, list):
        candidates = candidates[0] if candidates else {}
    candidates = candidates if isinstance(candidates, dict) else payload
    encoded = candidates.get('b64_json') or candidates.get('image')
    image_url = candidates.get('url') or candidates.get('image_url')
    if encoded:
        try:
            out.write_bytes(base64.b64decode(encoded))
            validate_generated_image(out)
            return
        except Exception as error:
            raise _provider_error(provider, 'The provider returned invalid image data.', response.status_code, response.text) from error
    if image_url:
        image_response = None
        try:
            image_response = requests.get(image_url, timeout=120)
            image_response.raise_for_status()
            out.write_bytes(image_response.content)
            validate_generated_image(out)
            return
        except (requests.RequestException, ImageGenerationError) as error:
            raise _provider_error(provider, error, getattr(image_response, 'status_code', None)) from error
    raise _provider_error(provider, 'The provider response contained no image data.', response.status_code, response.text)


def _generate_image(prompt, out):
    key = current_app.config.get('IMAGE_API_KEY')
    if not key:
        raise ImageGenerationError('Image generation is not configured. Please add the required image-generation API key.', 'Google Gemini')
    custom_url = current_app.config.get('IMAGE_API_URL')
    if custom_url:
        try:
            response = requests.post(
                custom_url,
                headers={'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'},
                json={'model': current_app.config['IMAGE_MODEL'], 'prompt': prompt, 'response_format': 'b64_json'},
                timeout=120,
            )
            if not response.ok:
                raise _provider_error('custom HTTP image provider', response.reason, response.status_code, response.text)
            _write_provider_response(response, out, 'custom HTTP image provider')
            return
        except requests.RequestException as error:
            raise _provider_error('custom HTTP image provider', error) from error
    try:
        client = genai.Client(api_key=key)
        response = client.models.generate_content(
            model=current_app.config['IMAGE_MODEL'],
            contents=prompt,
            config=types.GenerateContentConfig(response_modalities=['TEXT', 'IMAGE']),
        )
        parts = getattr(response, 'parts', None) or [
            part for candidate in getattr(response, 'candidates', [])
            for part in getattr(getattr(candidate, 'content', None), 'parts', []) or []
        ]
        for part in parts:
            if getattr(part, 'inline_data', None) is not None:
                part.as_image().save(out)
                validate_generated_image(out)
                return
        raise _provider_error('Google Gemini', 'The response contained no generated image data.')
    except ImageGenerationError:
        raise
    except Exception as error:
        status = getattr(error, 'code', None) or getattr(error, 'status_code', None)
        raise _provider_error('Google Gemini', error, status) from error


def build_image_prompt(story, panel):
    character_profiles = '; '.join(profile.prompt_description() for profile in story.characters)
    if not character_profiles:
        character_profiles = story.character
    return f'''Create an actual finished comic-book illustration for panel "{panel.title}".
Story context: {story.title}. Theme and mood: {story.theme or story.tone}. Setting: {story.setting}.
Scene: {panel.scene}. Characters present: {', '.join(panel.characters)}.
Character appearance and fixed identity: {character_profiles}.
Action: {panel.actions}. Facial expression and emotion: {panel.emotion or story.tone}.
Environment and background: {panel.background or story.setting}. Camera angle: {panel.camera_angle or 'cinematic composition'}.
Visual style: {story.art_style}. Color mode: {story.colour_style}.
Create a complete illustrated panel with clear foreground, background, expressive poses, and consistent characters. Do not return text, SVG, HTML, JSON, captions, speech bubbles, watermarks, logos, placeholder graphics, or an empty image. Return actual generated image data only.'''


def generate_panel_image(story, panel, out, prompt=None, progress_callback=None):
    prompt = prompt or build_image_prompt(story, panel)
    max_retries = max(0, int(current_app.config.get('IMAGE_MAX_RETRIES', 3)))
    base_delay = max(0.1, float(current_app.config.get('IMAGE_BACKOFF_SECONDS', 5)))
    max_delay = max(base_delay, float(current_app.config.get('IMAGE_MAX_BACKOFF_SECONDS', 120)))
    for retry_number in range(max_retries + 1):
        try:
            _generate_image(prompt, out)
            validate_generated_image(out)
            return True
        except ImageRateLimitError as error:
            if retry_number >= max_retries:
                raise ImageGenerationError('Image generation quota is currently unavailable. Please try again later or configure an image-generation API with available quota.', error.provider, error.status) from error
            delay = error.retry_after if error.retry_after is not None else min(base_delay * (2 ** retry_number), max_delay)
            if progress_callback:
                progress_callback('rate_limited', delay)
            time.sleep(delay)
        except ImageGenerationError:
            raise


def generate_test_image(prompt, out):
    _generate_image(prompt, out)
    validate_generated_image(out)
    return True
