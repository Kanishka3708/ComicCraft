import base64
import re
import time
from pathlib import Path

import requests
from flask import current_app
from google import genai
from google.genai import types
from PIL import Image,ImageDraw,ImageFont


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
    normalized_error = error_text.lower()
    rate_limited = status == 429 or any(term in normalized_error for term in ('resource_exhausted', 'rate limit', 'rate_limit', 'quota'))
    quota_exhausted = 'perday' in normalized_error or 'quota is exhausted' in normalized_error
    if quota_exhausted:
        return ImageGenerationError('Image generation quota is currently unavailable. Please try again later or configure an image-generation API with available quota.', provider, status or 429)
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


def make_default_panel_image(story,panel,out,panel_number):
    palettes=[((20,34,66),(255,191,92),(90,198,190)),((54,28,72),(255,211,96),(239,126,145)),((25,42,60),(157,144,255),(83,181,204)),((28,68,57),(245,198,86),(117,195,157)),((65,38,30),(228,125,67),(234,183,91))]
    background,accent,secondary=palettes[(panel_number-1)%len(palettes)]
    image=Image.new('RGB',(1200,800),background)
    draw=ImageDraw.Draw(image)
    title_font=ImageFont.load_default(size=34)
    body_font=ImageFont.load_default(size=20)
    draw.rounded_rectangle((28,28,1172,772),radius=26,fill=background,outline=accent,width=10)
    draw.rectangle((70,175,1130,580),fill=secondary,outline=accent,width=8)
    horizon=380+(panel_number%3)*28
    draw.rectangle((70,horizon,1130,580),fill=accent)
    draw.polygon([(110,380),(330,245),(530,380)],fill=background)
    draw.polygon([(690,380),(900,210),(1120,380)],fill=background)
    draw.ellipse((470,230,730,490),fill=secondary,outline=background,width=8)
    draw.ellipse((535,310,565,340),fill=background)
    draw.ellipse((635,310,665,340),fill=background)
    draw.arc((535,340,665,430),0,180,fill=background,width=8)
    draw.polygon([(400,700),(600,455),(800,700)],fill=accent,outline=background)
    draw.line((120,610,1080,610),fill=accent,width=8)
    draw.text((78,78),f'PANEL {panel_number}',font=title_font,fill=accent)
    draw.text((78,650),panel.title[:70],font=body_font,fill=secondary)
    image.save(out,format='PNG')
    validate_generated_image(out)


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
    prompt = f'''Create an actual finished comic-book illustration for panel "{panel.title}".
Story context: {story.title}. Theme and mood: {story.theme or story.tone}. Setting: {story.setting}.
Genre: {story.genre}. Target audience: {story.target_audience}. Language: {story.language}.
Scene: {panel.scene}. Characters present: {', '.join(panel.characters)}.
Character appearance and fixed identity: {character_profiles}.
Action: {panel.actions}. Facial expression and emotion: {panel.emotion or story.tone}.
Environment and background: {panel.background or story.setting}. Camera angle: {panel.camera_angle or 'cinematic composition'}.
Visual style: {story.art_style}. Color mode: {story.colour_style}. Page orientation: {story.orientation}.
Character visual style: {story.character_visual_style}. Background style: {story.background_style}. Lighting and mood: {story.lighting_mood}.
Create a complete illustrated panel with clear foreground, background, expressive poses, and consistent characters. Apply all settings above consistently to every panel. Do not return text, SVG, HTML, JSON, captions, speech bubbles, watermarks, logos, placeholder graphics, or an empty image. Return actual generated image data only.'''
    current_app.logger.info('FINAL IMAGE PROMPT SETTINGS: genre=%s | visual_style=%s | color=%s | orientation=%s | character_visual=%s | background=%s | lighting=%s', story.genre, story.art_style, story.colour_style, story.orientation, story.character_visual_style, story.background_style, story.lighting_mood)
    current_app.logger.debug('FINAL IMAGE PROMPT: %s', prompt)
    return prompt


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
