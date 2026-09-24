import json
from io import BytesIO
from pathlib import Path
from flask import Blueprint,render_template,jsonify,request,send_file,current_app
from io import BytesIO
from PIL import Image
from uuid import uuid4
from pydantic import ValidationError
from .models import GenerateRequest,ComicStory
from .services.comic_service import generate_comic
from .exporters import export_pdf
from .image_generator import generate_panel_image,build_image_prompt
main_bp=Blueprint('main',__name__)
@main_bp.get('/')
def index(): return render_template('index.html')
@main_bp.get('/health')
def health(): return jsonify(status='ok',service='ComicCraft',mode='demo' if current_app.config['DEMO_MODE'] else 'gemini')
@main_bp.post('/api/generate')
def generate():
    try:
        req=GenerateRequest.model_validate(request.get_json(silent=True) or {})
        story,assets,source=generate_comic(req); data=story.model_dump(); data.update(assets=assets,source=source); return jsonify(data)
    except ValidationError as e: return jsonify(error='Invalid input',details=str(e)),400
    except Exception as e: return jsonify(error='Image generation failed. Try again.',details=str(e)),502
@main_bp.post('/api/export-pdf')
def pdf():
    try:
        data=request.get_json(silent=True) or {}; story=ComicStory.model_validate(data.get('story',data)); assets=data.get('assets',[])
        stream=export_pdf(story,assets,Path(current_app.root_path)/'static'/'generated')
        return send_file(stream,mimetype='application/pdf',as_attachment=True,download_name='comiccraft-comic.pdf')
    except Exception as e: return jsonify(error='PDF export failed',details=str(e)),400
@main_bp.post('/api/download-json')
def story_json():
    data=request.get_json(silent=True) or {}; story=ComicStory.model_validate(data.get('story',data)); stream=BytesIO(json.dumps(story.model_dump(),indent=2,ensure_ascii=False).encode())
    return send_file(stream,mimetype='application/json',as_attachment=True,download_name='comiccraft-story.json')

@main_bp.post('/api/panel/regenerate')
def regenerate_panel():
    try:
        data=request.get_json(silent=True) or {}; story=ComicStory.model_validate(data.get('story',data)); index=int(data.get('panel_index',0));
        if index<0 or index>=len(story.panels): return jsonify(error='Invalid panel index'),400
        if not current_app.config['IMAGE_API_KEY']: return jsonify(error='Image generation failed. Configure IMAGE_API_KEY and try again.'),503
        panel=story.panels[index]; prompt=str(data.get('prompt') or build_image_prompt(story,panel)); out=Path(current_app.root_path)/'static'/'generated'/f'comic_{uuid4().hex}_panel_{index+1}.png'
        if not generate_panel_image(story,panel,out,prompt): return jsonify(error='Image generation failed. Try again.'),502
        panel.image_prompt=prompt; panel.image_status='generated'; panel.image_error=''
        return jsonify(asset=f'/static/generated/{out.name}',panel=panel.model_dump())
    except Exception as e: return jsonify(error='Image generation failed. Try again.',details=str(e)),500

@main_bp.post('/api/export-image')
def export_image():
    try:
        data=request.get_json(silent=True) or {}; assets=data.get('assets',[]); fmt=str(data.get('format','png')).lower(); images=[]
        for asset in assets:
            name=Path(str(asset)).name; path=Path(current_app.root_path)/'static'/'generated'/name
            if not path.exists(): raise ValueError('Generated image is missing.')
            images.append(Image.open(path).convert('RGB'))
        if not images: raise ValueError('No generated images available.')
        width=max(image.width for image in images); thumb_h=width*2//3; canvas=Image.new('RGB',(width,thumb_h*len(images)),(16,18,40))
        for index,image in enumerate(images): canvas.paste(image.resize((width,thumb_h)),(0,index*thumb_h))
        stream=BytesIO(); output='JPEG' if fmt in ('jpg','jpeg') else 'PNG'; canvas.save(stream,format=output,quality=92); stream.seek(0)
        return send_file(stream,mimetype='image/jpeg' if output=='JPEG' else 'image/png',as_attachment=True,download_name=f'comiccraft-comic.{"jpg" if output=="JPEG" else "png"}')
    except Exception as e: return jsonify(error='Image export failed',details=str(e)),400
