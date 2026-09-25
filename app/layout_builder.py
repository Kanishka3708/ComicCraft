from pathlib import Path
from .image_generator import build_image_prompt,generate_panel_image,make_default_panel_image,ImageGenerationError
from flask import current_app
from uuid import uuid4
def build_assets(story,outdir,progress_callback=None):
    outdir.mkdir(parents=True,exist_ok=True); assets=[]
    for i,panel in enumerate(story.panels,1):
        panel.image_prompt=build_image_prompt(story,panel)
        png=outdir/f'comic_{uuid4().hex}_panel_{i}.png'
        try:
            if progress_callback:
                progress_callback('panel_started', i, len(story.panels))
            if not current_app.config['USE_GEMINI'] or not current_app.config['IMAGE_API_KEY']:
                raise ImageGenerationError('Image generation is not configured.', 'Google Gemini')
            generate_panel_image(story,panel,png,progress_callback=(lambda event, delay: progress_callback(event, i, len(story.panels), delay) if progress_callback else None))
            panel.image_status='generated'; panel.image_error=''
        except ImageGenerationError as error:
            current_app.logger.warning('[IMAGE] AI generation failed for panel %s: %s',i,error)
            make_default_panel_image(story,panel,png,i)
            panel.image_status='fallback'; panel.image_error='AI image unavailable - using default comic image.'
            current_app.logger.info('[IMAGE] Using local fallback image for panel %s',i)
        current_app.logger.info('[IMAGE] Panel %s image resolved: %s',i,png)
        assets.append('/static/generated/'+png.name)
    return assets
