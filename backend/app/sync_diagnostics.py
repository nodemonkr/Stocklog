from __future__ import annotations

import json
import logging
import os
import re
import threading
import traceback
import uuid
from contextvars import ContextVar, Token
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
PROJECT_ROOT = Path(__file__).resolve().parents[2]
SYNC_LOG_DIR = PROJECT_ROOT / "runtime" / "sync-error-logs"
SYNC_LOG_DIR.mkdir(parents=True, exist_ok=True)

_current_log: ContextVar[str | None] = ContextVar("stocklog_sync_diagnostic_log", default=None)
_write_lock = threading.Lock()
_handler_lock = threading.Lock()
_handler_installed = False

# Intentionally broad: diagnostic files are meant to be shareable with a developer.
# Never persist access tokens, cookies, passwords, client secrets, API keys, or account numbers.
_SECRET_PATTERNS = (
    re.compile(r"(?i)(authorization\s*[:=]\s*bearer\s+)[^\s,;\]\}\)]+"),
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+\-/=]+"),
    re.compile(r"(?i)((?:api[_-]?key|x[_-]?api[_-]?key|client[_-]?secret|access[_-]?token|refresh[_-]?token|password|passwd|jwt[_-]?secret|secret)\s*[:=]\s*)[^\s,;\]\}\)]+"),
    re.compile(r"(?i)(\"(?:api[_-]?key|x[_-]?api[_-]?key|client[_-]?secret|access[_-]?token|refresh[_-]?token|password|passwd|jwt[_-]?secret|secret|authorization|cookie|set[_-]?cookie)\"\s*:\s*\")[^\"]*(\")"),
    re.compile(r"(?i)((?:cookie|set-cookie|x-api-key)\s*[:=]\s*)[^\r\n,;\]\}\)]+"),
)
_ACCOUNT_PATTERN = re.compile(r"(?i)((?:account(?:_no)?|acnt_no)\s*[:=]\s*)[0-9\-]{6,}")
_ACCOUNT_JSON_PATTERN = re.compile(r'(\"(?:account(?:_no)?|acnt_no)\"\s*:\s*\")[0-9\-]{6,}(\")', re.I)


def redact_diagnostic(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list, tuple)):
        try:
            text = json.dumps(value, ensure_ascii=False, default=str)
        except Exception:
            text = str(value)
    else:
        text = str(value)
    for pattern in _SECRET_PATTERNS:
        if pattern.groups >= 2:
            text = pattern.sub(r"\1***REDACTED***\2", text)
        else:
            text = pattern.sub(r"\1***REDACTED***", text)
    text = _ACCOUNT_PATTERN.sub(r"\1***REDACTED***", text)
    text = _ACCOUNT_JSON_PATTERN.sub(r"\1***REDACTED***\2", text)
    return text


def _safe_label(value: str, default: str = "sync") -> str:
    cleaned = re.sub(r"[^A-Za-z0-9가-힣._-]+", "-", str(value or "").strip()).strip("-._")
    return (cleaned or default)[:64]


def _path_for(filename: str) -> Path:
    name = Path(str(filename or "")).name
    if not name or name != str(filename or "") or not name.endswith(".txt"):
        raise ValueError("invalid diagnostic filename")
    path = (SYNC_LOG_DIR / name).resolve()
    if path.parent != SYNC_LOG_DIR.resolve():
        raise ValueError("invalid diagnostic path")
    return path


def _prune_logs(max_files: int = 250, max_age_days: int = 90) -> None:
    try:
        files = sorted((p for p in SYNC_LOG_DIR.glob("*.txt") if p.is_file()), key=lambda p: p.stat().st_mtime, reverse=True)
        now = datetime.now().timestamp()
        for idx, path in enumerate(files):
            too_many = idx >= max_files
            too_old = (now - path.stat().st_mtime) > max_age_days * 86400
            if too_many or too_old:
                try:
                    path.unlink()
                except OSError:
                    pass
    except Exception:
        pass


def begin_sync_diagnostic(kind: str, *, run_id: str = "", metadata: dict | None = None) -> str:
    now = datetime.now(KST)
    stamp = now.strftime("%Y%m%d_%H%M%S_%f")[:-3]
    filename = f"{stamp}_{_safe_label(kind)}_{uuid.uuid4().hex[:6]}.txt"
    path = _path_for(filename)
    header = [
        "StockLog synchronization diagnostic log",
        f"created_at_kst={now.isoformat()}",
        f"kind={redact_diagnostic(kind)}",
        f"run_id={redact_diagnostic(run_id)}",
        f"pid={os.getpid()}",
    ]
    if metadata:
        header.append(f"metadata={redact_diagnostic(metadata)}")
    header.append("NOTE=Secrets/tokens/passwords/account numbers are masked before writing.")
    with _write_lock:
        path.write_text("\n".join(header) + "\n\n", encoding="utf-8")
    _prune_logs()
    return filename


def append_sync_diagnostic(
    filename: str | None,
    level: str,
    event: str,
    *,
    details: dict | str | None = None,
    exc: BaseException | None = None,
) -> None:
    if not filename:
        return
    try:
        path = _path_for(filename)
        now = datetime.now(KST).isoformat()
        lines = [f"[{now}] [{str(level or 'INFO').upper()}] {redact_diagnostic(event)}"]
        if details not in (None, ""):
            lines.append(f"details={redact_diagnostic(details)}")
        if exc is not None:
            lines.append(f"exception_type={type(exc).__name__}")
            lines.append(f"exception={redact_diagnostic(exc)}")
            tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
            lines.append("traceback=\n" + redact_diagnostic(tb))
        block = "\n".join(lines) + "\n\n"
        with _write_lock:
            with path.open("a", encoding="utf-8") as handle:
                handle.write(block)
    except Exception:
        # Diagnostics must never be able to fail a synchronization job.
        return


def current_sync_diagnostic() -> str | None:
    return _current_log.get()


def activate_sync_diagnostic(filename: str | None) -> Token:
    return _current_log.set(filename)


def deactivate_sync_diagnostic(token: Token | None) -> None:
    if token is None:
        return
    try:
        _current_log.reset(token)
    except Exception:
        pass


class _SyncDiagnosticHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        filename = current_sync_diagnostic()
        if not filename:
            return
        try:
            details = {
                "logger": record.name,
                "module": record.module,
                "function": record.funcName,
                "line": record.lineno,
                "message": record.getMessage(),
            }
            exc = None
            if record.exc_info and record.exc_info[1]:
                exc = record.exc_info[1]
            append_sync_diagnostic(filename, record.levelname, "BACKEND_LOG", details=details, exc=exc)
        except Exception:
            return


def install_sync_diagnostic_handler() -> None:
    global _handler_installed
    if _handler_installed:
        return
    with _handler_lock:
        if _handler_installed:
            return
        handler = _SyncDiagnosticHandler(level=logging.WARNING)
        logging.getLogger().addHandler(handler)
        _handler_installed = True


def list_sync_diagnostics(limit: int = 100) -> list[dict]:
    items = []
    for path in sorted(SYNC_LOG_DIR.glob("*.txt"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            stat = path.stat()
            items.append({
                "filename": path.name,
                "size": stat.st_size,
                "modified_at": datetime.fromtimestamp(stat.st_mtime, KST).isoformat(),
            })
        except OSError:
            continue
        if len(items) >= max(1, min(int(limit or 100), 250)):
            break
    return items


def diagnostic_path(filename: str) -> Path:
    path = _path_for(filename)
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(filename)
    return path
