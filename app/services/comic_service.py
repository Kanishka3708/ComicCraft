from pathlib import Path
from flask import current_app
from ..models import ComicStory,ComicPanel,GenerateRequest
from ..gemini_flash import generate_story as live_generate
from ..layout_builder import build_assets

def demo_story(req):
    tone_steps={
        'adventure': [('The Map in the Margins',f'{req.character} spots a hand-drawn map hidden inside a forgotten book.'),('Beyond the Locked Door',f'{req.character} follows the map to a sealed door beneath {req.setting}.'),('The Choice',f'When the floor gives way, {req.character} must choose between the treasure and a trapped stranger.'),('The Brave Detour',f'{req.character} abandons the shortcut, solves the old mechanism, and opens a way out.'),('A Story Worth Telling',f'{req.character} returns with a new friend and a secret map ready for the next journey.')],
        'comedy': [('The Great Mix-Up',f'{req.character} reaches for a quiet book but accidentally activates every alarm in {req.setting}.'),('The Very Serious Clue',f'A trail of flying bookmarks leads {req.character} to a tiny detective hat.'),('The Chase',f'{req.character} races after the runaway catalogue cart while trying to look completely innocent.'),('The Unexpected Suspect',f'The culprit turns out to be a helpful cat that has been alphabetizing everything.'),('A Happy Ending',f'{req.character} solves the case, earns a snack, and officially hires the cat as assistant.')],
        'mystery': [('The Unsent Letter',f'{req.character} finds a letter addressed to someone who vanished from {req.setting} years ago.'),('The Repeating Symbol',f'The same silver symbol appears on three shelves and in the dust by a hidden stairway.'),('The False Trail',f'{req.character} follows a convincing clue that leads to an empty room and a ticking clock.'),('The Missing Page',f'{req.character} realizes the final clue was torn from the letter and hidden in plain sight.'),('The Answer Beneath',f'{req.character} uncovers the truth: the vanished writer built a secret archive to protect a dangerous idea.')],
        'fantasy': [('The Ember Seed',f'{req.character} discovers a warm, glowing seed beneath the oldest stone in {req.setting}.'),('The Door of Vines',f'The seed awakens a vine-covered doorway to a kingdom hidden behind the walls.'),('The Silent Dragon',f'{req.character} meets a young dragon whose stolen voice is locked inside a crystal.'),('The Name of Courage',f'{req.character} speaks the dragon\'s true name and breaks the crystal without a sword.'),('Dawn Over Two Worlds',f'The dragon returns the magic to the kingdom, while {req.character} carries one ember home.')],
        'science fiction': [('The Signal',f'{req.character} receives a three-second distress signal from beyond the roof of {req.setting}.'),('The Pocket Door',f'A palm-sized portal opens, revealing a city drifting between the stars.'),('The Power Drain',f'The portal starts collapsing and pulls every light in the building toward it.'),('The Impossible Fix',f'{req.character} combines an old machine with a clever circuit to stabilize the gateway.'),('A New Frequency',f'The distant city is safe, and {req.character} becomes the first person to answer its call.')],
        'drama': [('The Empty Chair',f'{req.character} returns to {req.setting} and finds the chair that belonged to someone they miss.'),('The Unfinished Work',f'A half-finished project reveals a promise that {req.character} never got to keep.'),('The Hard Conversation',f'{req.character} finally tells the truth instead of hiding behind an easy answer.'),('The First Step',f'With help from an unexpected ally, {req.character} completes one small part of the unfinished work.'),('Room for Tomorrow',f'{req.character} leaves the place changed, carrying grief honestly and hope carefully.')],
    }
    steps=tone_steps.get(req.tone.lower(),tone_steps['adventure'])
    steps=steps[:req.panel_count]
    if len(steps)<req.panel_count: steps=(steps*((req.panel_count+len(steps)-1)//len(steps)))[:req.panel_count]
    dialogue_lines=['I think this is the beginning.','There has to be another way.','I will not leave anyone behind.','The answer was here all along.','This is only the first chapter.']
    characters=req.characters or ([{'name':req.character}] if req.character else [])
    character_names=[item.name if hasattr(item,'name') else item['name'] for item in characters]
    profiles=characters if req.characters else []
    setting=req.custom_setting or req.setting
    panels=[]
    for index,((title,scene),dialogue) in enumerate(zip(steps,(dialogue_lines*((req.panel_count+4)//5))[:req.panel_count]),1):
        panels.append(ComicPanel(title=title,scene=scene,caption=f'{title}: {scene}',narration=f'{req.character or "The hero"} follows the thread of the story through {setting}, guided by {req.premise or req.story_description or "a strange new discovery"}.',dialogue=dialogue,characters=character_names,actions=scene,background=setting,emotion=req.tone,camera_angle='Cinematic medium shot'))
    return ComicStory(title=req.story_title or f'{(req.character or "Untitled").title()}\'s {req.genre} Comic',character=req.character or (character_names[0] if character_names else 'Hero'),setting=setting,tone=req.tone,art_style=req.custom_art_style or req.art_style,colour_style=req.custom_colour_style or req.colour_style,theme=req.theme,characters=profiles,panels=panels)

def generate_comic(req):
    story=None; source='demo'
    if current_app.config['USE_GEMINI'] and current_app.config['GEMINI_API_KEY']:
        try: story=live_generate(req); source='gemini'
        except Exception: story=None
    if story is None: story=demo_story(req)
    assets=build_assets(story,Path(current_app.root_path)/'static'/'generated')
    return story,assets,source
