import os
class Config:
    SECRET_KEY=os.getenv('SECRET_KEY','comiccraft-development-key')
    GEMINI_API_KEY=os.getenv('GEMINI_API_KEY','').strip()
    IMAGE_API_KEY=os.getenv('IMAGE_API_KEY','').strip() or GEMINI_API_KEY
    IMAGE_API_URL=os.getenv('IMAGE_API_URL','').strip()
    TEXT_MODEL=os.getenv('TEXT_MODEL','gemini-2.0-flash')
    IMAGE_MODEL=os.getenv('IMAGE_MODEL','gemini-2.0-flash-preview-image-generation')
    USE_GEMINI=os.getenv('USE_GEMINI','1').strip().lower() in ('1','true','yes')
    MAX_PANELS=int(os.getenv('MAX_PANELS','5'))
    IMAGE_MAX_RETRIES=int(os.getenv('IMAGE_MAX_RETRIES','3'))
    IMAGE_BACKOFF_SECONDS=float(os.getenv('IMAGE_BACKOFF_SECONDS','5'))
    IMAGE_MAX_BACKOFF_SECONDS=float(os.getenv('IMAGE_MAX_BACKOFF_SECONDS','120'))
    DEMO_MODE=not USE_GEMINI or not bool(GEMINI_API_KEY)
