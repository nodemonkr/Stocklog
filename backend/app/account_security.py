from __future__ import annotations


class AccountSecurityError(ValueError):
    pass


def validate_admin_password(password: str, username: str = "") -> str:
    """Validate an administrator-issued replacement password without normalizing it."""
    value = str(password or "")
    if len(value) < 8 or len(value) > 128:
        raise AccountSecurityError("비밀번호는 8자 이상 128자 이하로 입력해주세요.")
    if not value.strip():
        raise AccountSecurityError("공백으로만 된 비밀번호는 사용할 수 없습니다.")
    if username and value.casefold() == str(username).casefold():
        raise AccountSecurityError("아이디와 동일한 비밀번호는 사용할 수 없습니다.")
    return value


def membership_change_error(
    *,
    acting_admin_id: int,
    target_user_id: int,
    current_tier: str,
    next_tier: str,
    admin_count: int,
) -> str | None:
    current = str(current_tier or "").upper()
    requested = str(next_tier or "").upper()
    if int(target_user_id) == int(acting_admin_id) and requested != "ADMIN":
        return "현재 로그인한 관리자 본인의 관리자 등급은 해제할 수 없습니다."
    if current == "ADMIN" and requested != "ADMIN" and int(admin_count or 0) <= 1:
        return "최소 1명의 관리자 계정은 유지되어야 합니다."
    return None
