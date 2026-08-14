import hashlib
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def generate_token() -> str:
    return f"kit_{secrets.token_urlsafe(32)}"


def hash_token(token: str) -> str:
    # Deterministic (not argon2) is deliberate: a bearer token has to be
    # looked up *by itself* (no username to look up first, unlike a
    # password), and argon2's per-call random salt makes that impossible.
    # A fast hash of a high-entropy 256-bit random token is the standard
    # approach for API keys (same as GitHub/Stripe).
    return hashlib.sha256(token.encode()).hexdigest()
