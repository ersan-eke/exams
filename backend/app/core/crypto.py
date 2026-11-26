"""Encryption of stored third-party tokens. The key is read at call time so tests and rotation need no reimport."""

from cryptography.fernet import Fernet, MultiFernet

from app.core import config


def _fernet() -> MultiFernet:
    if not config.INTEGRATIONS_KEY:
        raise RuntimeError("INTEGRATIONS_KEY not set")
    return MultiFernet([Fernet(k.strip()) for k in config.INTEGRATIONS_KEY.split(",")])


def encrypt(plain: str) -> str:
    return _fernet().encrypt(plain.encode()).decode()


def decrypt(token: str, ttl: int | None = None) -> str:
    """With `ttl` (seconds), a token older than that raises InvalidToken."""
    return _fernet().decrypt(token.encode(), ttl=ttl).decode()
