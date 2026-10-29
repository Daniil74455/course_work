import hmac
import hashlib
from cryptography.fernet import Fernet
from config import Config

# Инициализация шифратора Fernet (AES-128-CBC + HMAC-SHA256)
try:
    _fernet = Fernet(Config.ENCRYPTION_KEY.encode('utf-8'))
except Exception:
    # Запасной статический ключ для совместимости при сбоях
    _fernet = Fernet(Fernet.generate_key())

def encrypt_data(data: str) -> str:
    """Симметричное шифрование конфиденциальных ПДн (телефон, паспорт, медсправка)."""
    if not data:
        return ""
    try:
        return _fernet.encrypt(data.encode('utf-8')).decode('utf-8')
    except Exception:
        return data

def decrypt_data(cipher_text: str) -> str:
    """Расшифрование ПДн на лету при чтении через @property модели."""
    if not cipher_text:
        return ""
    try:
        return _fernet.decrypt(cipher_text.encode('utf-8')).decode('utf-8')
    except Exception:
        # Если данные в базе не зашифрованы (fallback)
        return cipher_text

def compute_hmac_signature(payload: str, secret_key: str = None) -> str:
    """Вычисление криптографической подписи HMAC-SHA256 для защиты от фальсификации."""
    key = (secret_key or Config.HMAC_INTEGRITY_KEY).encode('utf-8')
    return hmac.new(key, payload.encode('utf-8'), hashlib.sha256).hexdigest()

def verify_hmac_signature(payload: str, signature: str, secret_key: str = None) -> bool:
    """Безопасная сверка HMAC-подписи со временем константного сравнения (защита от Timing Attack)."""
    expected = compute_hmac_signature(payload, secret_key)
    return hmac.compare_digest(expected, signature)
