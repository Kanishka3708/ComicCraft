from google import genai
from google.genai import types
from .models import ComicStory
from .config import Config

def generate_story(req):
    if not Config.GEMINI_API_KEY: return None
    client=genai.Client(api_key=Config.GEMINI_API_KEY)
    profiles='; '.join(profile.prompt_description() for profile in req.characters) or req.character
    story_source = req.story_description or req.premise or 'Create a compelling original comic story.'
    prompt=f'''You are ComicCraft, an expert comic-story planner. Treat the user's story as the primary source of truth. Do not replace it with any default, demo, or sample story. Use the following story exactly as the basis for the comic: {story_source}.
Create exactly {req.panel_count} coherent comic panels that follow the same sequence of events in the provided story. Every panel must include a distinct scene, characters, action, background, camera angle, emotion, narration, short dialogue, and an image_prompt. Preserve these character details in every relevant panel: {profiles}. Do not invent unrelated plot points, locations, or characters. Return only JSON matching the supplied schema.
Title: {req.story_title}
Story description: {story_source}
Genre: {req.genre}
Setting: {req.custom_setting or req.setting}
Theme: {req.theme}
Tone: {req.tone}
Art style: {req.custom_art_style or req.art_style}
Colour style: {req.custom_colour_style or req.colour_style}
Target audience: {req.target_audience}
Language: {req.language}
Orientation: {req.orientation}
Character visual style: {req.character_visual_style}
Background style: {req.background_style}
Lighting and mood: {req.lighting_mood}
Panel planning mode: {req.panel_mode}
Manual panel details: {req.panel_details if req.panel_mode == 'manual' else 'Create the panel breakdown automatically.'}
Premise: {req.premise}'''
    response=client.models.generate_content(model=Config.TEXT_MODEL,contents=prompt,config=types.GenerateContentConfig(temperature=0.3,response_mime_type='application/json',response_schema=ComicStory))
    if not response.text: raise RuntimeError('Gemini returned an empty response.')
    return ComicStory.model_validate_json(response.text)
