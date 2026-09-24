from pathlib import Path
from flask import current_app
from google import genai
from google.genai import types
from PIL import Image,ImageDraw,ImageFont
import base64
import requests

def build_image_prompt(story,panel):
    character_profiles='; '.join(profile.prompt_description() for profile in story.characters)
    if not character_profiles: character_profiles=story.character
    return f'''Create an actual comic-book illustration for panel "{panel.title}".
Story: {story.title}. Theme and mood: {story.theme or story.tone}. Setting: {story.setting}.
Scene: {panel.scene}. Action: {panel.actions}. Emotion: {panel.emotion or story.tone}. Camera: {panel.camera_angle or 'cinematic composition'}.
Characters and fixed visual identity: {character_profiles}.
Visual direction: {story.art_style}. Colour direction: {story.colour_style}.
Create a unique illustration for this panel, with clear foreground and background, expressive poses, strong composition, and no readable text, captions, speech bubbles, watermarks, or logos. Preserve every character's appearance exactly across panels.'''

def generate_panel_image(story,panel,out,prompt=None):
    key=current_app.config.get('IMAGE_API_KEY')
    if not key: return False
    prompt=prompt or build_image_prompt(story,panel)
    custom_url=current_app.config.get('IMAGE_API_URL')
    if custom_url:
        response=requests.post(custom_url,headers={'Authorization':f'Bearer {key}'},json={'model':current_app.config['IMAGE_MODEL'],'prompt':prompt,'response_format':'b64_json'},timeout=120)
        response.raise_for_status()
        if response.headers.get('content-type','').startswith('image/'):
            out.write_bytes(response.content); return True
        payload=response.json(); encoded=payload.get('b64_json') or payload.get('image') or payload.get('data',{}).get('b64_json')
        if encoded:
            out.write_bytes(base64.b64decode(encoded)); return True
        return False
    client=genai.Client(api_key=key)
    response=client.models.generate_content(model=current_app.config['IMAGE_MODEL'],contents=prompt,config=types.GenerateContentConfig(response_modalities=['TEXT','IMAGE']))
    parts=getattr(response,'parts',None) or [part for candidate in getattr(response,'candidates',[]) for part in getattr(getattr(candidate,'content',None),'parts',[]) or []]
    for part in parts:
        if getattr(part,'inline_data',None) is not None:
            part.as_image().save(out); return True
    return False

def make_demo_image(story,panel,out):
    tone=story.tone.lower()
    palettes={
        'adventure':((16,42,67),(246,189,96),(56,163,165),(254,243,199)),
        'comedy':((61,31,74),(255,207,86),(242,132,130),(255,243,176)),
        'mystery':((23,27,45),(155,138,251),(77,143,172),(232,228,255)),
        'fantasy':((23,63,53),(242,193,78),(114,189,163),(229,246,213)),
        'science fiction':((16,29,59),(103,232,249),(129,140,248),(219,234,254)),
        'drama':((58,39,50),(229,159,113),(184,107,119),(250,225,221)),
    }
    bg,accent,secondary,card=next((value for key,value in palettes.items() if key in tone),palettes['adventure'])
    style=story.art_style.lower()
    if 'manga' in style:
        bg,accent,secondary,card=((242,242,238),(24,24,24),(176,176,176),(255,255,250))
    elif 'watercolor' in style:
        bg,accent,secondary,card=((224,238,232),(104,137,126),(171,202,190),(255,249,232))
    elif 'retro' in style:
        bg,accent,secondary,card=((58,39,29),(209,116,55),(224,171,88),(255,226,166))
    image=Image.new('RGB',(1200,800),bg); draw=ImageDraw.Draw(image)
    line=4 if 'manga' in style or 'watercolor' in style else 12 if 'minimal' not in style else 7
    title_font=ImageFont.truetype('C:/Windows/Fonts/arialbd.ttf',42)
    body_font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',22)
    draw.rounded_rectangle((35,35,1165,765),radius=28,fill=card,outline=accent,width=line)
    draw.text((85,82),panel.title,font=title_font,fill=bg)
    draw.line((70,165,1130,165),fill=accent,width=8)
    if 'retro' in style:
        for x in range(90,1120,24):
            for y in range(190,560,24): draw.ellipse((x,y,x+5,y+5),fill=accent)
    elif 'manga' in style:
        for offset in range(-300,1300,70): draw.line((600,390,offset,185),fill=secondary,width=2)
    elif 'watercolor' in style:
        for offset in range(0,5): draw.ellipse((120+offset*190,210+offset*18,370+offset*190,420+offset*18),fill=secondary)
    scene=panel.scene[:105]
    setting=story.setting.lower()
    if 'space' in setting or 'science' in tone:
        for x,y in [(150,235),(260,310),(930,230),(1010,360),(820,270)]: draw.ellipse((x,y,x+8,y+8),fill=accent)
        draw.ellipse((870,205,1010,345),fill=secondary,outline=accent,width=8)
        draw.arc((905,240,975,310),0,360,fill=bg,width=7)
    elif 'library' in setting or 'book' in setting:
        for x in range(150,1050,110): draw.rectangle((x,315,x+70,500),fill=secondary,outline=bg,width=5)
        draw.rectangle((120,500,1080,535),fill=accent,outline=bg,width=5)
    elif 'forest' in setting or 'garden' in setting:
        for x in [180,930]:
            draw.rectangle((x,380,x+30,535),fill=accent)
            draw.polygon([(x-85,400),(x+15,220),(x+115,400)],fill=secondary,outline=bg)
    else:
        draw.rectangle((135,390,1065,535),fill=secondary,outline=bg,width=6)
        draw.polygon([(210,390),(600,230),(990,390)],fill=accent,outline=bg)
    if 'mystery' in tone:
        draw.ellipse((155,205,285,335),fill=accent,outline=bg,width=5)
        draw.line((220,335,220,465),fill=accent,width=8)
        draw.ellipse((190,420,250,480),outline=accent,width=8)
    elif 'comedy' in tone:
        for x,y in [(180,250),(980,300),(300,220),(900,430)]: draw.ellipse((x,y,x+28,y+28),fill=accent,outline=bg,width=4)
        draw.arc((870,220,1040,390),0,300,fill=accent,width=10)
    elif 'fantasy' in tone:
        for x,y in [(170,230),(980,230),(900,400)]:
            draw.polygon([(x,y-25),(x+8,y-8),(x+28,y),(x+8,y+8),(x,y+28),(x-8,y+8),(x-28,y),(x-8,y-8)],fill=accent)
    elif 'adventure' in tone:
        draw.ellipse((920,210,1030,320),outline=accent,width=9)
        draw.line((975,265,975,205),fill=accent,width=6); draw.line((975,265,1030,285),fill=accent,width=6)
    elif 'drama' in tone:
        for x in range(170,1020,100): draw.line((x,210,x-35,520),fill=secondary,width=4)
    draw.ellipse((475,255,725,505),fill=secondary,outline=bg,width=line)
    draw.ellipse((535,335,558,358),fill=bg); draw.ellipse((642,335,665,358),fill=bg)
    draw.arc((535,365,665,450),0,180,fill=bg,width=line)
    draw.polygon([(420,700),(600,470),(780,700)],fill=accent,outline=bg)
    draw.rounded_rectangle((90,575,1110,710),radius=18,fill=card,outline=bg,width=5)
    draw.text((125,600),scene,font=body_font,fill=bg)
    draw.text((125,655),f'{story.art_style} • {story.tone}',font=body_font,fill=bg)
    image.save(out,format='PNG')
