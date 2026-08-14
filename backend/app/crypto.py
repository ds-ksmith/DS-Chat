import base64
import hashlib

from cryptography.fernet import Fernet

from app.config import settings


def _fernet() -> Fernet:
    # Derives a stable Fernet key from SESSION_SECRET rather than requiring
    # a new env var -- this is the only reversible secret this app stores
    # in the database (SMTP password), so it gets real encryption at rest,
    # but doesn't need its own deployment configuration to do it.
    key = hashlib.sha256(settings.session_secret.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    return _fernet().decrypt(ciphertext.encode()).decode()
