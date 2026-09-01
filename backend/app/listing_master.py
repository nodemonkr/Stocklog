from __future__ import annotations

import re
import threading
import time
from typing import Iterable

import httpx
from bs4 import BeautifulSoup

KIND_CORP_LIST_URL = "https://kind.krx.co.kr/corpgeneral/corpList.do"
_KIND_MARKETS = {
    "KOSPI": "stockMkt",
    "KOSDAQ": "kosdaqMkt",
}
_CACHE_TTL_SECONDS = 6 * 60 * 60
_cache_lock = threading.Lock()
_cache_at = 0.0
_cache_rows: list[dict] = []


def _clean_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _valid_company_name(value: str) -> bool:
    value = _clean_text(value)
    if not value or len(value) > 120:
        return False
    if re.fullmatch(r"[0-9./-]+", value):
        return False
    blocked = {"회사명", "종목코드", "업종", "주요제품", "상장일", "결산월", "대표자명", "홈페이지", "지역"}
    return value not in blocked


def parse_kind_company_html(html: str, market: str) -> list[dict]:
    """Parse KRX KIND listed-company master with explicit header validation.

    v3.68.3 guessed the company-name cell from its position next to the code.
    That is too risky for a security master.  We now prefer an explicit
    ``회사명``/``종목코드`` header mapping and mark fallback parses as
    unverified so they can never overwrite an existing trusted name.
    """
    market = str(market or "").upper()
    soup = BeautifulSoup(html or "", "html.parser")
    out: list[dict] = []
    seen: set[str] = set()

    for table in soup.find_all("table") or [soup]:
        trs = table.find_all("tr")
        header_map = None
        header_pos = -1
        for pos, tr in enumerate(trs):
            cells = [_clean_text(x.get_text(" ", strip=True)) for x in tr.find_all(["td", "th"])]
            name_idx = next((i for i, c in enumerate(cells) if c in {"회사명", "법인명"}), None)
            code_idx = next((i for i, c in enumerate(cells) if "종목코드" in c or c == "종목 코드"), None)
            if name_idx is not None and code_idx is not None:
                header_map = (name_idx, code_idx)
                header_pos = pos
                break

        if header_map:
            name_idx, code_idx = header_map
            for tr in trs[header_pos + 1:]:
                cells = [_clean_text(x.get_text(" ", strip=True)) for x in tr.find_all(["td", "th"])]
                if max(name_idx, code_idx) >= len(cells):
                    continue
                compact = re.sub(r"[^0-9]", "", cells[code_idx])
                if not re.fullmatch(r"\d{1,6}", compact):
                    continue
                code = compact.zfill(6)
                name = _clean_text(cells[name_idx])
                if code in seen or not _valid_company_name(name):
                    continue
                seen.add(code)
                out.append({"code": code, "name": name, "market": market, "source": "KRX_KIND", "name_verified": True})

    if out:
        return out

    # Conservative compatibility fallback.  These rows may add a missing code,
    # but merge_company_master will not let an unverified name overwrite an
    # existing provider/database name.
    for tr in soup.find_all("tr"):
        cells = [_clean_text(x.get_text(" ", strip=True)) for x in tr.find_all(["td", "th"])]
        if len(cells) < 2:
            continue
        code_idx = None
        code = ""
        for idx, cell in enumerate(cells):
            compact = re.sub(r"[^0-9]", "", cell)
            if re.fullmatch(r"\d{6}", compact):
                code_idx, code = idx, compact
                break
        if code_idx is None or code in seen:
            continue
        name = ""
        for idx in (code_idx - 1, 0, code_idx + 1):
            if 0 <= idx < len(cells) and _valid_company_name(cells[idx]) and cells[idx] != code:
                name = cells[idx]
                break
        if not name:
            continue
        seen.add(code)
        out.append({"code": code, "name": name, "market": market, "source": "KRX_KIND_FALLBACK", "name_verified": False})
    return out


def _decode_response(response: httpx.Response) -> str:
    charset = response.charset_encoding
    if charset:
        try:
            return response.content.decode(charset, errors="strict")
        except Exception:
            pass
    for enc in ("utf-8", "cp949", "euc-kr"):
        try:
            return response.content.decode(enc, errors="strict")
        except Exception:
            continue
    return response.content.decode("utf-8", errors="replace")


def _request_params(market_type: str) -> dict[str, str | int]:
    return {
        "method": "download",
        "pageIndex": 1,
        "currentPageSize": 5000,
        "orderMode": 3,
        "orderStat": "D",
        "marketType": market_type,
        "searchType": 13,
        "fiscalYearEnd": "all",
        "location": "all",
    }


def fetch_kind_company_master(*, force: bool = False, timeout: float = 12.0) -> list[dict]:
    """Return KOSPI/KOSDAQ listed-company master from KRX KIND.

    Results are cached in-process for six hours.  Failure raises to the caller;
    synchronization code can then safely continue with Kiwoom while recording
    that the secondary master was unavailable.
    """
    global _cache_at, _cache_rows
    now = time.monotonic()
    with _cache_lock:
        if not force and _cache_rows and now - _cache_at <= _CACHE_TTL_SECONDS:
            return [dict(x) for x in _cache_rows]

    rows: list[dict] = []
    headers = {
        "User-Agent": "Mozilla/5.0 (StockLog listed-company master verification)",
        "Accept": "text/html,application/xhtml+xml,application/vnd.ms-excel,*/*",
        "Referer": "https://kind.krx.co.kr/corpgeneral/corpList.do?method=loadInitPage",
    }
    with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client:
        for market, market_type in _KIND_MARKETS.items():
            response = client.get(KIND_CORP_LIST_URL, params=_request_params(market_type))
            response.raise_for_status()
            parsed = parse_kind_company_html(_decode_response(response), market)
            if len(parsed) < 300:
                raise RuntimeError(f"KRX KIND {market} 상장법인 목록이 비정상적으로 적습니다: {len(parsed)}개")
            rows.extend(parsed)

    # Security code is unique across the two company markets.
    deduped = {x["code"]: x for x in rows}
    result = list(deduped.values())
    if len(result) < 1500:
        raise RuntimeError(f"KRX KIND 전체 상장법인 목록이 비정상적으로 적습니다: {len(result)}개")
    with _cache_lock:
        _cache_rows = [dict(x) for x in result]
        _cache_at = time.monotonic()
    return result


def find_kind_company(query: str) -> list[dict]:
    term = _clean_text(query).casefold()
    if not term:
        return []
    rows = fetch_kind_company_master()
    exact: list[dict] = []
    partial: list[dict] = []
    for row in rows:
        code = str(row.get("code") or "")
        name = _clean_text(row.get("name")).casefold()
        if term == code.casefold() or term == name:
            exact.append(row)
        elif term in code.casefold() or term in name:
            partial.append(row)
    return exact + partial


def merge_company_master(primary_rows: Iterable[dict], kind_rows: Iterable[dict]) -> tuple[list[dict], dict]:
    """Merge Kiwoom and KRX without losing name history.

    KRX rows parsed through explicit headers are authoritative for the current
    official company name.  A changed provider name is retained as an alias.
    Unverified fallback parses can fill a missing security but never overwrite
    an existing name.
    """
    merged: dict[str, dict] = {}
    primary_codes: set[str] = set()
    for raw in primary_rows:
        row = dict(raw)
        code = str(row.get("code") or "").strip()
        if not re.fullmatch(r"\d{6}", code):
            continue
        primary_codes.add(code)
        row.setdefault("name_source", "KIWOOM")
        row.setdefault("name_aliases", [])
        row.setdefault("name_verified", True)
        merged[code] = row

    kind_added = kind_verified = name_changes = unverified_skipped = 0
    for raw in kind_rows:
        row = dict(raw)
        code = str(row.get("code") or "").strip()
        if not re.fullmatch(r"\d{6}", code):
            continue
        kind_name = _clean_text(row.get("name"))
        verified = bool(row.get("name_verified", False))
        if code in merged:
            current = merged[code]
            current_name = _clean_text(current.get("name"))
            aliases = list(current.get("name_aliases") or [])
            if verified and _valid_company_name(kind_name):
                if current_name and current_name != kind_name and current_name not in aliases:
                    aliases.append(current_name)
                    name_changes += 1
                current["name"] = kind_name
                current["name_source"] = "KRX_KIND"
                current["name_verified"] = True
                current["name_aliases"] = aliases
                current["official_name_changed"] = current_name != kind_name
            elif kind_name and current_name != kind_name:
                # Keep the trusted primary name when the KRX parser was not
                # able to prove which column contained the company name.
                unverified_skipped += 1
            current["market"] = row.get("market") or current.get("market")
            current["kind_verified"] = verified
            kind_verified += int(verified)
        else:
            if not _valid_company_name(kind_name):
                continue
            row["kind_verified"] = verified
            row["name_source"] = "KRX_KIND" if verified else "KRX_KIND_FALLBACK"
            row["name_aliases"] = []
            merged[code] = row
            kind_added += 1

    return list(merged.values()), {
        "primary_total": len(primary_codes),
        "merged_total": len(merged),
        "kind_added_missing_from_primary": kind_added,
        "kind_verified_existing": kind_verified,
        "official_name_changes": name_changes,
        "unverified_name_overwrites_blocked": unverified_skipped,
    }

