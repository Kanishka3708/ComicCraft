from pathlib import Path
from .image_generator import build_image_prompt,generate_panel_image,make_demo_image
from flask import current_app
from uuid import uuid4
def build_assets(story,outdir):
    outdir.mkdir(parents=True,exist_ok=True); assets=[]
    for i,panel in enumerate(story.panels,1):
        panel.image_prompt=build_image_prompt(story,panel)
        png=outdir/f'comic_{uuid4().hex}_panel_{i}.png'
        if current_app.config['USE_GEMINI'] and current_app.config['IMAGE_API_KEY']:
            if not generate_panel_image(story,panel,png):
                panel.image_status='failed'; panel.image_error='Image generation failed. Try again.'
                raise RuntimeError(panel.image_error)
            panel.image_status='generated'
        else:
            make_demo_image(story,panel,png); panel.image_status='local_demo'; panel.image_error='Configure IMAGE_API_KEY to generate provider-backed artwork.'
        assets.append('/static/generated/'+png.name)
    return assets
