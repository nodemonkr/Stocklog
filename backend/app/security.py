from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from jose import JWTError, jwt
from passlib.context import CryptContext

from .config import settings

SECRET_KEY = settings.jwt_secret
ALGORITHM = "HS256"
EXPIRE_MINUTES = settings.access_token_expire_minutes

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return pwd_context.verify(password, hashed)


def create_access_token(subject: str, auth_version: int = 0) -> str:
    from datetime import datetime, timedelta, timezone

    exp = datetime.now(timezone.utc) + timedelta(minutes=EXPIRE_MINUTES)
    return jwt.encode(
        {"sub": subject, "av": max(0, int(auth_version or 0)), "exp": exp},
        SECRET_KEY,
        algorithm=ALGORITHM,
    )


def decode_token_claims(token: str) -> tuple[str, int] | None:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        subject = str(payload.get("sub") or "").strip()
        if not subject:
            return None
        auth_version = max(0, int(payload.get("av", 0) or 0))
        return subject, auth_version
    except (JWTError, TypeError, ValueError):
        return None


def decode_token(token: str) -> str | None:
    claims = decode_token_claims(token)
    return claims[0] if claims else None


def _fernet_for(secret: str) -> Fernet:
    digest = hashlib.sha256(secret.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def _fernet() -> Fernet:
    return _fernet_for(SECRET_KEY)


def encrypt_secret(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt_secret(value: str) -> str:
    encrypted = value.encode()
    try:
        return _fernet().decrypt(encrypted).decode()
    except InvalidToken:
        # v3.34.1 and earlier read SECRET_KEY while the shipped environment
        # used JWT_SECRET. Existing credentials may therefore have been
        # encrypted with this historical fallback key. Keep read compatibility
        # so an upgrade does not suddenly disconnect Kiwoom. New writes always
        # use the configured JWT_SECRET.
        legacy_secret = "CHANGE_THIS_TO_A_LONG_RANDOM_STRING"
        if SECRET_KEY != legacy_secret:
            try:
                return _fernet_for(legacy_secret).decrypt(encrypted).decode()
            except InvalidToken:
                pass
        raise ValueError(
            "저장된 암호화 값을 현재 JWT_SECRET으로 복호화할 수 없습니다. "
            "JWT_SECRET 변경 여부를 확인하거나 키움 Key/Secret을 다시 저장해 주세요."
        )
