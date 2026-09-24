from google import genai
from google.genai import types
from .models import ComicStory
from .config import Config

def generate_story(req):
    if not Config.GEMINI_API_KEY: return None
    client=genai.Client(api_key=Config.GEMINI_API_KEY)
    profiles='; '.join(profile.prompt_description() for profile in req.characters) or req.character
    prompt=f'''You are ComicCraft, an expert comic-story planner. Analyze the user's story and create exactly {req.panel_count} coherent comic panels. Every panel must include a distinct scene, characters, action, background, camera angle, emotion, narration, short dialogue, and an image_prompt. Preserve these character details in every relevant panel: {profiles}. Return only JSON matching the supplied schema.
Title: {req.story_title}
Story description: {req.story_description or req.premise}
Genre: {req.genre}
Setting: {req.custom_setting or req.setting}
Theme: {req.theme}
Tone: {req.tone}
Art style: {req.custom_art_style or req.art_style}
Colour style: {req.custom_colour_style or req.colour_style}
Premise: {req.premise}'''
    response=client.models.generate_content(model=Config.TEXT_MODEL,contents=prompt,config=types.GenerateContentConfig(temperature=0.9,response_mime_type='application/json',response_schema=ComicStory))
    if not response.text: raise RuntimeError('Gemini returned an empty response.')
    return ComicStory.model_validate_json(response.text)
