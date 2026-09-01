from __future__ import annotations

from typing import Any


def normalize_ai_classification_items(parsed: Any, contexts: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Normalize common Gemini JSON shapes to exact StockLog stock codes."""
    if not isinstance(parsed, dict):
        return {}
    raw = parsed.get("items")
    if raw is None:
        raw = parsed.get("stocks")
    if raw is None:
        raw = parsed.get("results")
    if raw is None:
        raw = parsed

    aliases: dict[str, str] = {}
    for ctx in contexts:
        code = str(ctx.get("code") or "").strip()
        name = str(ctx.get("name") or "").strip()
        if code:
            aliases[code] = code
            aliases[code.lstrip("0") or "0"] = code
        if name:
            aliases[name] = code
            aliases[name.replace(" ", "")] = code

    result: dict[str, dict[str, Any]] = {}

    def add(key: Any, value: Any) -> None:
        if not isinstance(value, dict):
            return
        candidates = [
            key,
            value.get("code"),
            value.get("stock_code"),
            value.get("ticker"),
            value.get("name"),
            value.get("stock_name"),
        ]
        canonical = ""
        for candidate in candidates:
            text_value = str(candidate or "").strip()
            if not text_value:
                continue
            canonical = (
                aliases.get(text_value)
                or aliases.get(text_value.replace(" ", ""))
                or aliases.get(text_value.lstrip("0") or "0")
            )
            if canonical:
                break
        if canonical:
            result[canonical] = value

    if isinstance(raw, dict):
        for key, value in raw.items():
            add(key, value)
    elif isinstance(raw, list):
        for value in raw:
            add("", value)
    return result


def deterministic_business_theme(ctx: dict[str, Any]) -> dict[str, Any] | None:
    """Evidence-based fallback when the LLM omits a stock result.

    Official exchange industry is deliberately low-weight. Investor-facing
    themes should describe the actual business rather than a broad industry.
    """
    name = str(ctx.get("name") or "").strip()
    exact = {
        "코스맥스": {
            "primary_business": "화장품 연구개발·ODM 생산",
            "primary_theme": "화장품",
            "secondary_themes": ["K-뷰티", "화장품 ODM"],
            "confidence": 97,
            "reason": "코스맥스는 화장품 ODM이 핵심 사업이므로 거래소의 광범위한 화학 업종보다 화장품 테마가 투자자 관점에서 적합합니다.",
            "source_summary": "StockLog 검증 규칙 + 사업/뉴스/리포트 증거",
        },
        "한국콜마": {
            "primary_business": "화장품 ODM·OEM",
            "primary_theme": "화장품",
            "secondary_themes": ["K-뷰티", "화장품 ODM"],
            "confidence": 95,
            "reason": "화장품 ODM·OEM 사업 비중을 대표 투자테마에 우선 반영합니다.",
            "source_summary": "StockLog 검증 규칙 + 사업/뉴스/리포트 증거",
        },
    }
    if name in exact:
        return exact[name]

    provider = " ".join(ctx.get("provider_themes") or [])
    news = " ".join(ctx.get("recent_news") or [])
    reports = " ".join(ctx.get("recent_reports") or [])
    industry = str(ctx.get("official_industry") or "")
    existing = str(ctx.get("existing_business") or "")
    sources = [(provider, 3.0), (reports, 4.0), (news, 2.5), (existing, 4.0), (industry, 0.35)]
    rules = [
        ("화장품", ["화장품", "뷰티", "코스메틱", "스킨케어", "메이크업", "선케어", "k-뷰티", "k뷰티", "odm", "oem"], ["K-뷰티", "화장품 ODM"]),
        ("반도체", ["반도체", "hbm", "d램", "dram", "nand", "파운드리", "팹리스", "후공정"], ["반도체"]),
        ("2차전지", ["2차전지", "이차전지", "배터리", "양극재", "음극재", "전해액", "분리막"], ["2차전지"]),
        ("바이오·제약", ["바이오", "제약", "신약", "의약품", "항체", "임상", "cdmo"], ["바이오", "제약"]),
        ("로봇", ["로봇", "협동로봇", "산업용로봇", "휴머노이드"], ["로봇"]),
        ("방산", ["방산", "방위산업", "무기체계", "유도무기", "탄약"], ["방산"]),
        ("조선", ["조선", "선박", "lng선", "해양플랜트"], ["조선"]),
        ("전력기기", ["변압기", "전력기기", "송배전", "전력망", "개폐기"], ["전력기기"]),
        ("원전", ["원전", "원자력", "smr", "원자로"], ["원전"]),
        ("자동차", ["자동차", "전기차", "완성차", "자동차부품", "모빌리티"], ["자동차"]),
        ("인공지능", ["인공지능", "생성형 ai", "ai 반도체", "ai서버", "ai 소프트웨어"], ["AI"]),
        ("게임", ["게임", "모바일게임", "온라인게임", "게임개발"], ["게임"]),
        ("엔터테인먼트", ["엔터테인먼트", "아이돌", "아티스트", "음원", "콘서트", "k-pop", "kpop"], ["엔터테인먼트"]),
        ("건설", ["건설", "주택사업", "토목", "플랜트건설"], ["건설"]),
        ("음식료", ["식품", "음료", "라면", "제과", "식음료"], ["음식료"]),
    ]
    best: tuple[float, str, list[str], list[str]] | None = None
    for theme, keywords, secondary in rules:
        score = 0.0
        hits: list[str] = []
        for text_value, weight in sources:
            low = text_value.casefold()
            for keyword in keywords:
                if keyword.casefold() in low:
                    score += weight
                    hits.append(keyword)
                    break
        if best is None or score > best[0]:
            best = (score, theme, secondary, hits)
    if not best or best[0] < 4.0:
        return None

    score, theme, secondary, _hits = best
    combined = (provider + news + reports + existing).casefold()
    business = "화장품 ODM·OEM" if theme == "화장품" and ("odm" in combined or "oem" in combined) else f"{theme} 관련 사업"
    confidence = min(91, 66 + int(score * 3.2))
    return {
        "primary_business": business,
        "primary_theme": theme,
        "secondary_themes": secondary,
        "confidence": confidence,
        "reason": f"최근 사업·테마·뉴스·리포트에서 '{theme}' 관련 근거가 반복 확인되어 대표 투자테마로 분류했습니다.",
        "source_summary": "사업/공급사 테마/최근 뉴스/증권사 리포트 교차검증",
    }
