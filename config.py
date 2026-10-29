import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'default-autoschool-secret-key-2026')
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL', 'sqlite:///autoschool.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Ключи информационной безопасности
    ENCRYPTION_KEY = os.getenv('ENCRYPTION_KEY', 'aW1x9sdUG35VBYsR_iYy3Qmq6OQXj8Yw4g-IHFIyiwk=')
    HMAC_INTEGRITY_KEY = os.getenv('HMAC_INTEGRITY_KEY', 'autoschool-hmac-sha256-exam-integrity-salt-key-2026')

    # Безопасность сессий и cookie (согласно требованиям ИБ)
    PERMANENT_SESSION_LIFETIME = timedelta(minutes=15)
    SESSION_COOKIE_HTTPONLY = True      # Защита от кражи cookie через XSS (JavaScript document.cookie)
    SESSION_COOKIE_SAMESITE = 'Lax'     # Защита от межсайтовой подделки запросов (CSRF)
    SESSION_COOKIE_SECURE = False       # True при использовании HTTPS в production
    WTF_CSRF_TIME_LIMIT = 3600          # Срок жизни CSRF-токена 1 час
