import os
from dotenv import load_dotenv
load_dotenv()
from app import create_app
app = create_app()
if __name__ == '__main__':
    app.run(host=os.getenv('HOST','127.0.0.1'), port=int(os.getenv('PORT','5000')), debug=os.getenv('FLASK_DEBUG','1') in ('1','true','True'))
