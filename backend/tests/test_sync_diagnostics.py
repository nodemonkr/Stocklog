from backend.app.sync_diagnostics import (
    append_sync_diagnostic,
    begin_sync_diagnostic,
    diagnostic_path,
    list_sync_diagnostics,
)


def test_sync_diagnostic_masks_secrets_and_account_numbers():
    name = begin_sync_diagnostic(
        "pytest",
        run_id="run-1",
        metadata={"api_key": "SECRET_KEY_VALUE", "account_no": "1234567890"},
    )
    path = diagnostic_path(name)
    try:
        append_sync_diagnostic(
            name,
            "ERROR",
            "CLIENT_ERROR",
            details={
                "authorization": "Bearer TOKEN_VALUE",
                "password": "PASSWORD_VALUE",
                "cookie": "session=COOKIE_SECRET_VALUE",
                "x-api-key": "HEADER_API_SECRET",
            },
        )
        text = path.read_text(encoding="utf-8")
        assert "SECRET_KEY_VALUE" not in text
        assert "1234567890" not in text
        assert "TOKEN_VALUE" not in text
        assert "PASSWORD_VALUE" not in text
        assert "COOKIE_SECRET_VALUE" not in text
        assert "HEADER_API_SECRET" not in text
        assert "***REDACTED***" in text
    finally:
        path.unlink(missing_ok=True)


def test_sync_diagnostic_is_listed_and_rejects_path_traversal():
    name = begin_sync_diagnostic("pytest-list", run_id="run-2")
    path = diagnostic_path(name)
    try:
        assert name in {item["filename"] for item in list_sync_diagnostics(50)}
        try:
            diagnostic_path("../escape.txt")
        except ValueError:
            pass
        else:
            raise AssertionError("path traversal must be rejected")
    finally:
        path.unlink(missing_ok=True)
