import os
os.environ['GEMINI_API_KEY']=''
from app import create_app
from app.models import GenerateRequest
from app.services.comic_service import demo_story
def test_demo(): assert len(demo_story(GenerateRequest()).panels)==5
def test_health():
 c=create_app().test_client(); r=c.get('/health'); assert r.status_code==200 and r.get_json()['status']=='ok'
def test_generate():
 c=create_app().test_client(); r=c.post('/api/generate',json={'character':'Asha'}); assert r.status_code==200 and len(r.get_json()['panels'])==5
def test_pdf():
 c=create_app().test_client(); s=demo_story(GenerateRequest()).model_dump(); r=c.post('/api/export-pdf',json=s); assert r.status_code==200 and r.data[:4]==b'%PDF'
