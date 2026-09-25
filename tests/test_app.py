import os
os.environ['GEMINI_API_KEY']=''
from pathlib import Path
from PIL import Image
from app import create_app
from app.models import GenerateRequest
from app.services.comic_service import demo_story, generate_comic
def test_blank_story_title_does_not_fallback_to_character_name():
    story = demo_story(GenerateRequest(character='Asha', story_title=''))
    assert story.title == 'Untitled Comic'

def test_custom_story_is_used_instead_of_demo_story():
    custom_story = (
        'One evening, Kani stays late at college to finish her project. '
        'While walking through an empty corridor, she discovers a glowing door that has never been there before. '
        'She opens it and finds a magical library filled with floating books. '
        'One book suddenly opens by itself and shows a picture of her future. '
        'Before she can read it, the library begins disappearing. '
        'Kani grabs the mysterious book and runs back through the door. '
        'The next morning, the door is gone—but the magical book is still on her desk, with one message written inside: "Your adventure has only begun."'
    )
    req = GenerateRequest(
        story_title='The Mysterious Door',
        story_description=custom_story,
        genre='Fantasy',
        panel_count=5,
        character='Kani',
        setting='College',
        tone='Mysterious and adventurous',
        art_style='Anime',
        theme='Mystery',
        target_audience='Young adult',
        language='English',
        orientation='Portrait',
    )
    story, _, _ = generate_comic(req)
    assert story.title == 'The Mysterious Door'
    assert any('glowing door' in panel.scene.lower() for panel in story.panels)
    assert 'the map in the margins' not in ' '.join(panel.title.lower() for panel in story.panels)
    assert 'door' in story.panels[0].scene.lower()


def test_create_page_starts_with_blank_story_title():
    client = create_app().test_client()
    response = client.get('/create/new')
    assert response.status_code == 200
    assert 'id="storyTitle" value=""' in response.get_data(as_text=True)

def test_demo(): assert len(demo_story(GenerateRequest()).panels)==5
def test_health():
 c=create_app().test_client(); r=c.get('/health'); assert r.status_code==200 and r.get_json()['status']=='ok'
def test_generate():
 c=create_app().test_client(); r=c.post('/api/generate',json={'character':'Asha'}); data=r.get_json(); assert r.status_code==200 and len(data['assets'])==5 and all(panel['image_status']=='fallback' for panel in data['panels'])
def test_pdf():
 c=create_app().test_client(); generated=c.post('/api/generate',json={'character':'Asha'}).get_json(); r=c.post('/api/export-pdf',json=generated); assert r.status_code==200 and r.data[:4]==b'%PDF'
def test_pdf_with_missing_asset():
 c=create_app().test_client(); s=demo_story(GenerateRequest()).model_dump(); s['assets']=[None]+[None]*(len(s['panels'])-1); r=c.post('/api/export-pdf',json=s); assert r.status_code==400 and b'image is missing' in r.data
def test_demo_panel_regenerate():
 c=create_app().test_client(); story=demo_story(GenerateRequest()).model_dump(); r=c.post('/api/panel/regenerate',json={'story':story,'panel_index':0,'prompt':'retry'}); assert r.status_code==200 and r.get_json()['panel']['image_status']=='fallback'

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

def test_selected_settings_reach_every_panel_prompt(monkeypatch,caplog):
 from app import image_generator,services
 from app.services import comic_service
 req=GenerateRequest(story_title='Settings test',story_description='A mystery',genre='Mystery',panel_count=5,character='Asha',art_style='Manga',colour_style='Black and White',orientation='Portrait',character_visual_style='Ink character sheets',background_style='Detailed library',lighting_mood='Moonlit suspense',target_audience='Young adult',language='English')
 monkeypatch.setattr(comic_service,'build_assets',lambda story,outdir,progress_callback=None: [])
 app=create_app()
 with app.app_context(),caplog.at_level('INFO'):
  story,_,_=comic_service.generate_comic(req)
  prompts=[image_generator.build_image_prompt(story,panel) for panel in story.panels]
 assert all(value in prompt for prompt in prompts for value in ('Mystery','Manga','Black and White','Portrait','Ink character sheets','Detailed library','Moonlit suspense'))
 assert 'FINAL IMAGE PROMPT SETTINGS' in caplog.text

def test_stream_logs_received_settings(caplog):
 app=create_app()
 payload={'genre':'Mystery','art_style':'Manga','colour_style':'Black and White','orientation':'Portrait','character_visual_style':'Ink character sheets','background_style':'Detailed library','lighting_mood':'Moonlit suspense','character':'Asha','panel_count':1}
 with app.test_client() as client,caplog.at_level('INFO'):
  client.post('/api/generate-stream',json=payload)
 assert 'RECEIVED COMIC SETTINGS' in caplog.text and 'Manga' in caplog.text and 'Moonlit suspense' in caplog.text
