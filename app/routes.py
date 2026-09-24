import json
import queue
import threading
from io import BytesIO
from pathlib import Path
from flask import Blueprint,render_template,jsonify,request,send_file,current_app,Response,stream_with_context
from io import BytesIO
from PIL import Image
from uuid import uuid4
from pydantic import ValidationError
from .models import GenerateRequest,ComicStory
from .services.comic_service import generate_comic
from .exporters import export_pdf
from .image_generator import generate_panel_image,generate_test_image,build_image_prompt,ImageGenerationError
main_bp=Blueprint('main',__name__)
@main_bp.get('/')
def index(): return render_template('index.html')
@main_bp.get('/create')
def create_page(): return render_template('index.html')
@main_bp.get('/create/new')
def new_create_page(): return render_template('create_new.html')
@main_bp.get('/health')
def health(): return jsonify(status='ok',service='ComicCraft',mode='demo' if current_app.config['DEMO_MODE'] else 'gemini')
@main_bp.post('/api/generate')
def generate():
    try:
        req=GenerateRequest.model_validate(request.get_json(silent=True) or {})
        story,assets,source=generate_comic(req); data=story.model_dump(); data.update(assets=assets,source=source); return jsonify(data)
    except ValidationError as e: return jsonify(error='Invalid input',details=str(e)),400
    except ImageGenerationError as e: return jsonify(error=str(e),stage='image_generation',provider=e.provider),502
    except Exception as e: return jsonify(error='Generation failed',details=str(e)),500

@main_bp.post('/api/generate-stream')
def generate_stream():
    try:
        req=GenerateRequest.model_validate(request.get_json(silent=True) or {})
    except ValidationError as e:
        return jsonify(error='Invalid input',details=str(e)),400
    events=queue.Queue()
    app=current_app._get_current_object()

    def progress(event,panel,total,delay=None):
        events.put({'type':event,'panel':panel,'total':total,'delay':delay})

    def worker():
        with app.app_context():
            try:
                story,assets,source=generate_comic(req,progress)
                data=story.model_dump(); data.update(assets=assets,source=source)
                events.put({'type':'complete','data':data})
            except ImageGenerationError as error:
                events.put({'type':'error','error':str(error),'provider':error.provider})
            except Exception as error:
                current_app.logger.exception('COMIC STREAM GENERATION ERROR')
                events.put({'type':'error','error':'Generation failed. Please try again.'})
            finally:
                events.put(None)

    threading.Thread(target=worker,daemon=True).start()

    @stream_with_context
    def event_stream():
        while True:
            event=events.get()
            if event is None:
                break
            yield f'data: {json.dumps(event)}\n\n'

    return Response(event_stream(),mimetype='text/event-stream',headers={'Cache-Control':'no-cache','X-Accel-Buffering':'no'})
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
        panel=story.panels[index]; prompt=str(data.get('prompt') or build_image_prompt(story,panel)); out=Path(current_app.root_path)/'static'/'generated'/f'comic_{uuid4().hex}_panel_{index+1}.png'
        if not current_app.config['USE_GEMINI'] or not current_app.config['IMAGE_API_KEY']:
            return jsonify(success=False,error='Image generation is not configured. Please add the required image-generation API key.',stage='image_generation'),503
        generate_panel_image(story,panel,out,prompt)
        panel.image_status='generated'
        panel.image_prompt=prompt; panel.image_error=''
        return jsonify(success=True,asset=f'/static/generated/{out.name}',panel=panel.model_dump())
    except ImageGenerationError as e:
        return jsonify(success=False,error=str(e),stage='image_generation',provider=e.provider),502
    except Exception as e: return jsonify(error='Image generation failed. Try again.',details=str(e)),500

@main_bp.post('/api/test-image-generation')
def test_image_generation():
    try:
        prompt=str((request.get_json(silent=True) or {}).get('prompt') or '').strip()
        if not prompt: return jsonify(success=False,error='A prompt is required.',stage='image_generation'),400
        out=Path(current_app.root_path)/'static'/'generated'/f'test_{uuid4().hex}.png'
        generate_test_image(prompt,out)
        return jsonify(success=True,image_url=f'/static/generated/{out.name}')
    except ImageGenerationError as e:
        return jsonify(success=False,error=str(e),stage='image_generation',provider=e.provider),502
    except Exception:
        current_app.logger.exception('IMAGE GENERATION ERROR: unexpected test route failure')
        return jsonify(success=False,error='Unexpected image generation failure.',stage='image_generation'),500

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
