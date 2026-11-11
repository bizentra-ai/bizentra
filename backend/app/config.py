import os
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///./businessos.db')
SECRET_KEY = os.environ['SECRET_KEY']
if len(SECRET_KEY) < 32:
    raise RuntimeError('SECRET_KEY must contain at least 32 characters')
ENVIRONMENT = os.getenv('ENVIRONMENT', 'development')
FRONTEND_URL = os.getenv('FRONTEND_URL', 'http://127.0.0.1:5173')
EMAIL_HOST = os.getenv('EMAIL_HOST', '')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', '587'))
EMAIL_USERNAME = os.getenv('EMAIL_USERNAME', '')
EMAIL_PASSWORD = os.getenv('EMAIL_PASSWORD', '')
EMAIL_FROM = os.getenv('EMAIL_FROM', '')
