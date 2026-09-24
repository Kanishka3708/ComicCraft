import os
os.environ['GEMINI_API_KEY']=''
from pathlib import Path
from PIL import Image
from app import create_app
from app.models import GenerateRequest
from app.services.comic_service import demo_story
def test_demo(): assert len(demo_story(GenerateRequest()).panels)==5
def test_health():
 c=create_app().test_client(); r=c.get('/health'); assert r.status_code==200 and r.get_json()['status']=='ok'
def test_generate():
 c=create_app().test_client(); r=c.post('/api/generate',json={'character':'Asha'}); assert r.status_code==502 and 'Image generation is not configured' in r.get_json()['error']
def test_pdf():
 c=create_app().test_client(); s=demo_story(GenerateRequest()).model_dump(); r=c.post('/api/export-pdf',json=s); assert r.status_code==400 and b'image is missing' in r.data
def test_pdf_with_missing_asset():
 c=create_app().test_client(); s=demo_story(GenerateRequest()).model_dump(); s['assets']=[None]+[None]*(len(s['panels'])-1); r=c.post('/api/export-pdf',json=s); assert r.status_code==400 and b'image is missing' in r.data
def test_demo_panel_regenerate():
 c=create_app().test_client(); story=demo_story(GenerateRequest()).model_dump(); r=c.post('/api/panel/regenerate',json={'story':story,'panel_index':0,'prompt':'retry'}); assert r.status_code==503 and 'Image generation is not configured' in r.get_json()['error']

def test_five_generated_images(monkeypatch, tmp_path):
 from app import layout_builder
 app=create_app(); app.config.update(USE_GEMINI=True,IMAGE_API_KEY='test-key')
 calls=[]
 def fake_generate(story,panel,out,progress_callback=None):
  calls.append(panel.title); Image.new('RGB',(32,32),(20,40,60)).save(out)
 monkeypatch.setattr(layout_builder,'generate_panel_image',fake_generate)
 with app.test_client() as client:
  response=client.post('/api/generate',json={'character':'Asha','panel_count':5})
 assert response.status_code==200
 payload=response.get_json(); assert len(calls)==5 and len(payload['assets'])==5
 for asset in payload['assets']:
  image_path=Path(app.root_path)/'static'/'generated'/Path(asset).name
  with Image.open(image_path) as image: assert image.width > 0 and image.height > 0

def test_rate_limit_retry_uses_delay(monkeypatch,tmp_path):
 from app import image_generator
 from app.models import ComicPanel,ComicStory
 app=create_app(); app.config.update(IMAGE_MAX_RETRIES=2,IMAGE_BACKOFF_SECONDS=5,IMAGE_MAX_BACKOFF_SECONDS=120)
 story=ComicStory(title='Test',character='Asha',setting='Library',tone='Adventure',art_style='Comic',panels=[ComicPanel(title='One',scene='A scene',caption='A caption',narration='Narration',dialogue='Hello')])
 calls=[]; delays=[]
 def fake_generate(prompt,out):
  calls.append(prompt)
  if len(calls)<3: raise image_generator.ImageRateLimitError('rate limited',retry_after=56)
  Image.new('RGB',(32,32),(20,40,60)).save(out)
 monkeypatch.setattr(image_generator,'_generate_image',fake_generate); monkeypatch.setattr(image_generator.time,'sleep',delays.append)
 with app.app_context(): image_generator.generate_panel_image(story,story.panels[0],tmp_path/'panel.png')
 assert len(calls)==3 and delays==[56,56]

def test_generation_stream_reports_all_panels(monkeypatch):
 from app import layout_builder
 app=create_app(); app.config.update(USE_GEMINI=True,IMAGE_API_KEY='test-key')
 def fake_generate(story,panel,out,progress_callback=None): Image.new('RGB',(32,32),(20,40,60)).save(out)
 monkeypatch.setattr(layout_builder,'generate_panel_image',fake_generate)
 with app.test_client() as client:
  response=client.post('/api/generate-stream',json={'character':'Asha','panel_count':5})
 body=response.get_data(as_text=True)
 assert response.status_code==200 and all(f'"panel": {number}' in body for number in range(1,6)) and '"type": "complete"' in body
