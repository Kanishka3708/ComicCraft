from pathlib import Path
from .image_generator import build_image_prompt,generate_panel_image,ImageGenerationError
from flask import current_app
from uuid import uuid4
def build_assets(story,outdir,progress_callback=None):
    if not current_app.config['USE_GEMINI'] or not current_app.config['IMAGE_API_KEY']:
        raise ImageGenerationError('Image generation is not configured. Please add the required image-generation API key.', 'Google Gemini')
    outdir.mkdir(parents=True,exist_ok=True); assets=[]
    for i,panel in enumerate(story.panels,1):
        panel.image_prompt=build_image_prompt(story,panel)
        png=outdir/f'comic_{uuid4().hex}_panel_{i}.png'
        try:
            if progress_callback:
                progress_callback('panel_started', i, len(story.panels))
            generate_panel_image(story,panel,png,progress_callback=(lambda event, delay: progress_callback(event, i, len(story.panels), delay) if progress_callback else None))
            panel.image_status='generated'
            panel.image_error=''
        except ImageGenerationError as error:
            panel.image_status='failed'
            panel.image_error=f'Panel {i} image generation failed. {error}'
            raise ImageGenerationError(panel.image_error,error.provider,error.status) from error
        assets.append('/static/generated/'+png.name)
    return assets
