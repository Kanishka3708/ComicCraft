import re
from pathlib import Path
from flask import current_app
from ..models import ComicStory,ComicPanel,GenerateRequest
from ..gemini_flash import generate_story as live_generate
from ..layout_builder import build_assets


def _story_keyword_phrases(raw_story):
    text = (raw_story or '').strip()
    if not text:
        return [], []
    sentences = [segment.strip() for segment in re.split(r'(?<=[.!?])\s+', text) if segment.strip()]
    return sentences, [sentence.lower() for sentence in sentences]


def _story_panel_titles(story_text, panel_count):
    lower = (story_text or '').lower()
    titles = []
    if 'door' in lower:
        titles.append('The Glowing Door')
    if 'library' in lower:
        titles.append('The Magical Library')
    if 'future' in lower or 'book' in lower:
        titles.append('The Book of the Future')
    if 'disappear' in lower or 'escape' in lower or 'run' in lower:
        titles.append('The Library Fades')
    if 'morning' in lower or 'message' in lower:
        titles.append('The Message on the Desk')
    while len(titles) < panel_count:
        fallbacks = ['The Hidden Discovery', 'The Unexpected Door', 'The Secret Room', 'The Escape', 'The Final Revelation']
        for item in fallbacks:
            if item not in titles:
                titles.append(item)
            if len(titles) >= panel_count:
                break
    return titles[:panel_count]


def _panel_scene_for_story(story_text, sentence_index, panel_index, character_name, setting):
    sentences = [segment.strip() for segment in re.split(r'(?<=[.!?])\s+', story_text) if segment.strip()]
    base = sentences[sentence_index] if sentence_index < len(sentences) else story_text
    lower = base.lower()
    if panel_index == 1:
        for idx, sentence in enumerate(sentences):
            s = sentence.lower()
            if 'door' in s or 'corridor' in s or 'empty corridor' in s:
                return sentence
        if 'college' in lower:
            return base
        return f'{character_name} stays late at {setting} and notices a mysterious glowing door that should not be there.'
    if panel_index == 2:
        for idx, sentence in enumerate(sentences):
            s = sentence.lower()
            if 'library' in s or 'floating books' in s or 'opens it' in s:
                return sentence
        return f'{character_name} opens the glowing door and discovers a magical library filled with floating books.'
    if panel_index == 3:
        for idx, sentence in enumerate(sentences):
            s = sentence.lower()
            if 'future' in s or 'book suddenly opens' in s or 'picture of her future' in s:
                return sentence
        return f'A mysterious book opens by itself and reveals a vision of {character_name}\'s future.'
    if panel_index == 4:
        for idx, sentence in enumerate(sentences):
            s = sentence.lower()
            if 'disappearing' in s or 'run back' in s or 'before she can read it' in s:
                return sentence
        return f'The magical library begins disappearing as {character_name} grabs the mysterious book and runs back through the door.'
    if panel_index == 5:
        for idx, sentence in enumerate(sentences):
            s = sentence.lower()
            if 'morning' in s or 'message' in s or 'desk' in s:
                return sentence
        return f'The next morning, the magical door is gone, but the mysterious book remains on {character_name}\'s desk with the final message: "Your adventure has only begun."'
    return base


def user_story_fallback(req):
    story_text = (req.story_description or req.premise or '').strip()
    title = (req.story_title or 'Untitled Comic').strip() or 'Untitled Comic'
    setting = (req.custom_setting or req.setting or 'Story world').strip() or 'Story world'
    character_name = (req.character or (req.characters[0].name if req.characters else 'Hero')).strip() or 'Hero'
    sentences = [segment.strip() for segment in re.split(r'(?<=[.!?])\s+', story_text) if segment.strip()]
    panel_count = max(1, min(int(req.panel_count or 5), 9))
    titles = _story_panel_titles(story_text, panel_count)
    panels = []
    for idx in range(panel_count):
        title_text = titles[idx] if idx < len(titles) else f'Panel {idx + 1}'
        sentence_index = 0
        if idx == 0:
            sentence_index = next((i for i, s in enumerate(sentences) if 'door' in s.lower() or 'corridor' in s.lower()), 0)
        elif idx == 1:
            sentence_index = next((i for i, s in enumerate(sentences) if 'library' in s.lower() or 'opens it' in s.lower() or 'floating books' in s.lower()), 0)
        elif idx == 2:
            sentence_index = next((i for i, s in enumerate(sentences) if 'future' in s.lower() or 'book' in s.lower()), 0)
        elif idx == 3:
            sentence_index = next((i for i, s in enumerate(sentences) if 'disappear' in s.lower() or 'run' in s.lower()), 0)
        elif idx == 4:
            sentence_index = next((i for i, s in enumerate(sentences) if 'morning' in s.lower() or 'message' in s.lower() or 'desk' in s.lower()), 0)
        scene = _panel_scene_for_story(story_text, sentence_index, idx + 1, character_name, setting)
        dialogue = 'The adventure has only just begun.' if idx == panel_count - 1 else f'{character_name}: This is only the beginning.'
        narration = f'{character_name} follows the exact events of the story through {setting}, moving from the first discovery to the final message.'
        if idx == 0:
            narration = f'{character_name} stays late at {setting}, notices the empty corridor, and finds the glowing door that should not exist.'
        elif idx == 1:
            narration = f'{character_name} opens the glowing door and steps into a magical library filled with floating books.'
        elif idx == 2:
            narration = f'A mysterious book opens on its own and reveals a glimpse of {character_name}\'s future.'
        elif idx == 3:
            narration = f'The magic begins to fade as {character_name} grabs the mysterious book and escapes through the door.'
        elif idx == 4:
            narration = f'The next morning brings the final clue: the door is gone, but the mysterious book remains with a message for {character_name}.'

        panel = ComicPanel(
            title=title_text,
            scene=scene,
            caption=f'{title_text}: {scene[:120]}',
            narration=narration,
            dialogue=dialogue,
            characters=[character_name],
            actions=scene,
            background=setting,
            emotion=req.tone or 'Mysterious',
            camera_angle='Cinematic wide shot' if idx in (0, 1) else 'Medium close-up',
        )
        panels.append(panel)
    return ComicStory(
        title=title,
        character=character_name,
        setting=setting,
        tone=req.tone or 'Adventure',
        art_style=req.custom_art_style or req.art_style,
        colour_style=req.custom_colour_style or req.colour_style,
        theme=req.theme or req.genre,
        genre=req.genre,
        target_audience=req.target_audience,
        language=req.language,
        orientation=req.orientation,
        character_visual_style=req.character_visual_style,
        background_style=req.background_style,
        lighting_mood=req.lighting_mood,
        characters=req.characters or ([{'name': character_name}] if character_name else []),
        panels=panels,
    )


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
    fallback_title = 'Untitled Comic'
    return ComicStory(title=(req.story_title or '').strip() or fallback_title,character=req.character or (character_names[0] if character_names else 'Hero'),setting=setting,tone=req.tone,art_style=req.custom_art_style or req.art_style,colour_style=req.custom_colour_style or req.colour_style,theme=req.theme,characters=profiles,panels=panels)

def generate_comic(req,progress_callback=None):
    story=None; source='demo'
    if req.story_description and req.story_description.strip():
        story = user_story_fallback(req)
        source = 'local-story-fallback'

    use_gemini = False
    gemini_key = ''
    try:
        use_gemini = bool(current_app.config['USE_GEMINI'])
        gemini_key = str(current_app.config.get('GEMINI_API_KEY', '')).strip()
    except RuntimeError:
        use_gemini = bool(__import__('os').getenv('USE_GEMINI', '1').strip().lower() in ('1', 'true', 'yes'))
        gemini_key = str(__import__('os').getenv('GEMINI_API_KEY', '')).strip()

    if use_gemini and gemini_key:
        try:
            story = live_generate(req)
            source = 'gemini'
        except Exception:
            if story is None:
                story = demo_story(req)
                source = 'demo'
    if story is None:
        story = demo_story(req)
        source = 'demo'
    story.genre=req.genre
    story.target_audience=req.target_audience
    story.language=req.language
    story.orientation=req.orientation
    story.character_visual_style=req.character_visual_style
    story.background_style=req.background_style
    story.lighting_mood=req.lighting_mood
    story.art_style=req.custom_art_style or req.art_style
    story.colour_style=req.custom_colour_style or req.colour_style

    try:
        assets=build_assets(story,Path(current_app.root_path)/'static'/'generated',progress_callback)
    except RuntimeError:
        assets=[]

    return story,assets,source
