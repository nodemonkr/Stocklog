import asyncio

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from .database import get_db, MonitorSessionLocal, run_monitor_blocking
from .models import User
from .security import decode_token_claims

bearer = HTTPBearer(auto_error=False)

def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
):
    if not credentials:
        raise HTTPException(401, "로그인이 필요합니다.")
    claims = decode_token_claims(credentials.credentials)
    if not claims:
        raise HTTPException(401, "로그인 정보가 만료되었거나 올바르지 않습니다.")
    username, token_auth_version = claims
    user = db.query(User).filter(User.username == username, User.is_active == True).first()
    if not user:
        # End the SELECT transaction before returning the 401.
        db.rollback()
        raise HTTPException(401, "사용자를 찾을 수 없습니다.")
    if int(getattr(user, "auth_version", 0) or 0) != int(token_auth_version):
        db.rollback()
        raise HTTPException(401, "비밀번호가 변경되어 다시 로그인해야 합니다.")

    # Authentication is a read-only lookup.  With expire_on_commit=False the
    # loaded User remains usable, while commit immediately returns the checked
    # out MySQL connection to the pool.  Previously every protected request
    # held this connection until its endpoint completed, including slow HTTP
    # calls to Kiwoom/DART/Gemini.
    db.commit()
    return user

def admin_user(user: User = Depends(current_user)):
    if not user.is_admin:
        raise HTTPException(403, "관리자 권한이 필요합니다.")
    return user


def _load_monitor_admin(username: str, token_auth_version: int):
    db = MonitorSessionLocal()
    try:
        user = db.query(User).filter(
            User.username == username, User.is_active == True
        ).first()
        if not user:
            raise HTTPException(401, "사용자를 찾을 수 없습니다.")
        if int(getattr(user, "auth_version", 0) or 0) != int(token_auth_version):
            raise HTTPException(401, "비밀번호가 변경되어 다시 로그인해야 합니다.")
        if not user.is_admin:
            raise HTTPException(403, "관리자 권한이 필요합니다.")
        db.expunge(user)
        return user
    finally:
        db.close()


async def admin_monitor_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
):
    """Authenticate admin monitor requests without consuming AnyIO's shared worker pool."""
    if not credentials:
        raise HTTPException(401, "로그인이 필요합니다.")
    claims = decode_token_claims(credentials.credentials)
    if not claims:
        raise HTTPException(401, "로그인 정보가 만료되었거나 올바르지 않습니다.")
    username, token_auth_version = claims
    try:
        return await asyncio.wait_for(run_monitor_blocking(_load_monitor_admin, username, token_auth_version),timeout=3.0)
    except asyncio.TimeoutError as exc:
        raise HTTPException(503,"관리자 동기화 모니터 인증 저장소가 지연되고 있습니다.") from exc
