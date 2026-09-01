from __future__ import annotations

"""StockLog deterministic investment-theme taxonomy.

The module deliberately separates an exchange industry from an investor-facing
investment theme.  Provider themes, reports, news and stored business text are
*evidence*; they never become a final theme without passing through this fixed
hierarchy.  That keeps labels stable across data providers and across sync runs.
"""

from collections import defaultdict
from dataclasses import dataclass
import re
from typing import Any, Iterable

THEME_ENGINE_VERSION = "stocklog-taxonomy-2026.08-v2"


@dataclass(frozen=True)
class ThemeRule:
    group: str
    subtheme: str
    keywords: tuple[str, ...]


def _r(group: str, subtheme: str, *keywords: str) -> ThemeRule:
    return ThemeRule(group, subtheme, tuple(dict.fromkeys((subtheme, *keywords))))


# Parent themes are intentionally broad and stable. Subthemes can evolve without
# breaking the top-level Smart Analysis filter.
THEME_RULES: tuple[ThemeRule, ...] = (
    _r("반도체", "메모리 반도체", "메모리반도체", "d램", "dram", "낸드", "nand", "ddr5", "lpddr"),
    _r("반도체", "HBM", "고대역폭메모리", "hbm3", "hbm3e", "hbm4"),
    _r("반도체", "시스템 반도체", "시스템반도체", "비메모리", "system semiconductor", "system ic"),
    _r("반도체", "팹리스", "fabless", "반도체 설계", "ic 설계", "칩 설계"),
    _r("반도체", "파운드리", "foundry", "반도체 위탁생산"),
    _r("반도체", "반도체 장비", "반도체장비", "웨이퍼 장비", "전공정 장비", "후공정 장비", "검사장비"),
    _r("반도체", "반도체 소재", "반도체소재", "포토레지스트", "불화수소", "실리콘 웨이퍼", "웨이퍼"),
    _r("반도체", "반도체 후공정", "반도체후공정", "패키징", "테스트하우스", "osat"),
    _r("반도체", "AI 반도체", "ai반도체", "ai 반도체", "npu", "gpu", "가속기 칩"),
    _r("반도체", "차량용 반도체", "차량용반도체", "automotive semiconductor"),
    _r("반도체", "CIS", "이미지센서", "cmos image sensor"),
    _r("반도체", "반도체", "semiconductor"),

    _r("화장품", "화장품 ODM/OEM", "화장품 odm", "화장품 oem", "odm 화장품", "oem 화장품", "코스메틱 odm"),
    _r("화장품", "K-뷰티", "k뷰티", "k-beauty", "k beauty"),
    _r("화장품", "스킨케어", "기초화장품", "기초 화장품", "선케어", "선크림"),
    _r("화장품", "색조화장품", "색조", "메이크업"),
    _r("화장품", "미용기기", "뷰티 디바이스", "미용 의료기기"),
    _r("화장품", "화장품", "코스메틱", "cosmetic", "뷰티"),

    _r("2차전지", "양극재", "양극활물질", "하이니켈", "ncm", "ncma", "lfp"),
    _r("2차전지", "음극재", "실리콘 음극", "흑연 음극"),
    _r("2차전지", "전해질", "전해액", "전해질염", "lipf6"),
    _r("2차전지", "분리막", "배터리 분리막"),
    _r("2차전지", "배터리 장비", "2차전지 장비", "이차전지 장비", "배터리 제조장비"),
    _r("2차전지", "폐배터리", "배터리 재활용", "배터리 리사이클"),
    _r("2차전지", "ESS", "에너지저장장치"),
    _r("2차전지", "2차전지", "이차전지", "배터리", "battery"),

    _r("자동차", "전기차", "ev", "electric vehicle"),
    _r("자동차", "자율주행", "adas", "첨단운전자보조"),
    _r("자동차", "자동차 부품", "자동차부품", "차량부품", "전장부품"),
    _r("자동차", "타이어", "tire"),
    _r("자동차", "수소차", "수소전기차", "수소연료전지차"),
    _r("자동차", "완성차", "완성 자동차", "완성차업체"),
    _r("자동차", "자동차", "모빌리티"),

    _r("디스플레이", "OLED", "amoled", "유기발광다이오드"),
    _r("디스플레이", "디스플레이 장비", "디스플레이장비"),
    _r("디스플레이", "디스플레이 소재", "디스플레이소재"),
    _r("디스플레이", "디스플레이", "lcd", "패널"),

    _r("전자부품", "PCB", "인쇄회로기판", "fpcb", "fc-bga", "fc bga"),
    _r("전자부품", "카메라 모듈", "카메라모듈", "렌즈 모듈"),
    _r("전자부품", "MLCC", "적층세라믹콘덴서"),
    _r("전자부품", "전자부품", "전자 부품"),
    _r("스마트폰", "스마트폰 부품", "스마트폰부품", "모바일 부품"),
    _r("스마트폰", "스마트폰", "휴대폰", "모바일폰"),

    _r("바이오·제약", "신약", "신약개발", "신약 개발", "임상시험", "임상 1상", "임상 2상", "임상 3상"),
    _r("바이오·제약", "바이오시밀러", "biosimilar"),
    _r("바이오·제약", "CDMO", "바이오 cdmo", "의약품 위탁개발생산"),
    _r("바이오·제약", "비만치료제", "glp-1", "glp1", "비만 치료제"),
    _r("바이오·제약", "항체·세포치료", "항체", "세포치료", "유전자치료"),
    _r("바이오·제약", "제약", "의약품", "pharma"),
    _r("바이오·제약", "바이오", "bio"),
    _r("의료기기", "진단", "진단키트", "체외진단", "분자진단"),
    _r("의료기기", "영상진단", "초음파", "ct 장비", "mri 장비"),
    _r("의료기기", "의료기기", "medical device"),

    _r("로봇", "협동로봇", "cobot"),
    _r("로봇", "휴머노이드", "인간형 로봇"),
    _r("로봇", "로봇 감속기", "감속기"),
    _r("로봇", "산업용 로봇", "산업용로봇", "공장 로봇"),
    _r("로봇", "서비스 로봇", "서비스로봇"),
    _r("로봇", "로봇", "robot"),

    _r("AI·소프트웨어", "생성형 AI", "생성형ai", "generative ai", "llm", "대규모언어모델"),
    _r("AI·소프트웨어", "AI 소프트웨어", "ai소프트웨어", "인공지능 소프트웨어", "machine learning", "머신러닝"),
    _r("AI·소프트웨어", "기업용 소프트웨어", "saas", "erp", "기업용 sw"),
    _r("AI·소프트웨어", "소프트웨어", "소프트웨어", "software"),
    _r("클라우드·데이터센터", "데이터센터", "data center", "datacenter", "idc"),
    _r("클라우드·데이터센터", "클라우드", "cloud"),
    _r("보안", "사이버보안", "정보보안", "보안솔루션", "cyber security"),
    _r("인터넷·플랫폼", "핀테크", "간편결제", "페이", "payment platform"),
    _r("인터넷·플랫폼", "플랫폼", "인터넷 플랫폼", "온라인 플랫폼"),

    _r("게임", "모바일게임", "모바일 게임"),
    _r("게임", "온라인게임", "온라인 게임", "pc게임"),
    _r("게임", "게임", "game"),
    _r("엔터테인먼트", "K-POP", "kpop", "k-pop", "아이돌", "아티스트", "음원", "콘서트"),
    _r("엔터테인먼트", "엔터테인먼트", "연예기획", "엔터사"),
    _r("미디어·콘텐츠", "웹툰·웹소설", "웹툰", "웹소설"),
    _r("미디어·콘텐츠", "영상 콘텐츠", "드라마", "영화", "ott 콘텐츠", "콘텐츠 제작"),
    _r("미디어·콘텐츠", "미디어", "방송", "콘텐츠"),

    _r("방산", "유도무기", "미사일", "유도탄"),
    _r("방산", "군용 항공", "전투기", "군용기"),
    _r("방산", "방산", "방위산업", "무기체계", "탄약", "군수"),
    _r("우주항공", "위성", "인공위성", "위성통신"),
    _r("우주항공", "발사체", "로켓", "우주발사체"),
    _r("우주항공", "항공", "항공기", "항공우주", "우주항공"),

    _r("조선", "LNG선", "lng 선", "lng carrier"),
    _r("조선", "조선 기자재", "조선기자재", "선박 기자재"),
    _r("조선", "해양플랜트", "해양 플랜트"),
    _r("조선", "조선", "선박", "shipbuilding"),
    _r("해운·물류", "해운", "해상운송", "컨테이너선 운송"),
    _r("해운·물류", "물류", "택배", "창고", "포워딩"),
    _r("항공·여행", "항공", "항공운송", "항공사"),
    _r("항공·여행", "여행", "여행사", "관광"),
    _r("레저", "카지노", "리조트", "골프", "레저"),

    _r("원전", "SMR", "소형모듈원전", "소형 모듈 원자로"),
    _r("원전", "원전 기자재", "원전기자재"),
    _r("원전", "원전", "원자력", "원자로", "nuclear"),
    _r("전력기기", "변압기", "transformer"),
    _r("전력기기", "송배전", "전력망", "그리드", "개폐기"),
    _r("전력기기", "전선", "케이블", "초고압 케이블"),
    _r("전력기기", "전력기기", "전력 장비"),
    _r("신재생에너지", "태양광", "태양전지", "solar"),
    _r("신재생에너지", "풍력", "해상풍력", "wind power"),
    _r("신재생에너지", "신재생에너지", "재생에너지", "renewable"),
    _r("수소", "수소연료전지", "연료전지"),
    _r("수소", "수소", "그린수소", "수전해"),

    _r("석유·가스", "정유", "정유사", "석유정제"),
    _r("석유·가스", "LNG", "액화천연가스", "천연가스"),
    _r("석유·가스", "석유·가스", "석유", "원유", "oil gas"),
    _r("화학·소재", "석유화학", "petrochemical"),
    _r("화학·소재", "정밀화학", "스페셜티 케미칼", "특수화학"),
    _r("화학·소재", "화학·소재", "화학", "chemical"),
    _r("철강·금속", "철강", "철강재", "강판", "열연", "냉연"),
    _r("철강·금속", "비철금속", "구리", "알루미늄", "아연", "니켈"),
    _r("철강·금속", "희토류", "희소금속"),

    _r("건설", "주택", "아파트", "주택사업"),
    _r("건설", "플랜트", "산업플랜트", "건설플랜트"),
    _r("건설", "인프라", "토목", "SOC"),
    _r("건설", "건설", "건축"),
    _r("건자재", "시멘트", "레미콘"),
    _r("건자재", "인테리어", "가구", "건축자재", "건자재"),
    _r("기계·산업장비", "공작기계", "머신툴"),
    _r("기계·산업장비", "산업자동화", "스마트팩토리", "공장자동화", "fa 장비"),
    _r("기계·산업장비", "기계·산업장비", "산업기계", "기계장비", "기계"),

    _r("통신", "5G", "5g 장비", "기지국"),
    _r("통신", "통신장비", "네트워크 장비"),
    _r("통신", "통신", "이동통신", "telecom"),
    _r("금융", "은행", "bank"),
    _r("증권", "증권", "증권사", "brokerage"),
    _r("보험", "보험", "생명보험", "손해보험"),
    _r("금융", "카드·캐피탈", "카드사", "캐피탈"),
    _r("금융", "금융", "지주", "금융지주"),

    _r("유통·소비", "면세점", "면세"),
    _r("유통·소비", "백화점", "대형마트", "편의점"),
    _r("유통·소비", "이커머스", "전자상거래", "온라인쇼핑"),
    _r("유통·소비", "유통", "소매", "리테일"),
    _r("음식료", "라면", "제과", "식품", "음식료"),
    _r("음식료", "주류", "맥주", "소주"),
    _r("음식료", "음료", "커피"),
    _r("의류·패션", "의류", "패션", "신발", "스포츠웨어"),
    _r("교육", "교육", "에듀테크", "학원"),
    _r("환경·폐기물", "폐기물", "재활용", "리사이클", "수처리", "환경"),
    _r("농업·비료", "비료", "농약", "종자", "농업", "스마트팜"),
)

# Explicit overrides are reserved for cases where the official industry is known
# to be a misleading investor-facing label or a diversified flagship needs a
# stable main group.  They are not the primary classification mechanism.
COMPANY_OVERRIDES: dict[str, dict[str, Any]] = {
    "코스맥스": {
        "primary_business": "화장품 연구개발·ODM 생산",
        "theme_group": "화장품",
        "theme_groups": ["화장품"],
        "subthemes": ["화장품 ODM/OEM", "K-뷰티"],
        "confidence": 99,
        "reason": "화장품 ODM이 핵심 사업이므로 거래소의 광범위한 화학 업종과 투자 테마를 분리했습니다.",
    },
    "한국콜마": {
        "primary_business": "화장품 ODM·OEM",
        "theme_group": "화장품",
        "theme_groups": ["화장품"],
        "subthemes": ["화장품 ODM/OEM", "K-뷰티"],
        "confidence": 98,
        "reason": "화장품 ODM·OEM 사업을 대표 투자테마로 우선합니다.",
    },
    "삼성전자": {
        "primary_business": "메모리·시스템 반도체 및 전자제품",
        "theme_group": "반도체",
        "theme_groups": ["반도체", "스마트폰", "디스플레이"],
        "subthemes": ["메모리 반도체", "HBM", "파운드리", "시스템 반도체"],
        "confidence": 99,
        "reason": "메모리·파운드리 등 반도체 사업이 핵심 투자 축이므로 상위 표준 테마를 반도체로 고정합니다.",
    },
    "제주반도체": {
        "primary_business": "메모리 반도체 설계·팹리스",
        "theme_group": "반도체",
        "theme_groups": ["반도체"],
        "subthemes": ["팹리스", "메모리 반도체", "시스템 반도체"],
        "confidence": 99,
        "reason": "팹리스·메모리 반도체는 모두 StockLog 표준 상위 테마 '반도체'의 세부 분야입니다.",
    },
    "SK하이닉스": {
        "primary_business": "메모리 반도체",
        "theme_group": "반도체",
        "theme_groups": ["반도체"],
        "subthemes": ["메모리 반도체", "HBM"],
        "confidence": 99,
        "reason": "메모리 반도체와 HBM 사업을 상위 표준 테마 반도체로 통합합니다.",
    },
}

# Official industry is only a low-weight fallback. These mappings are broad on
# purpose and never override stronger provider/business evidence.
SAFE_INDUSTRY_FALLBACK_GROUPS = {
    "금융", "보험", "통신", "건설", "건자재", "음식료", "의류·패션", "조선",
    "자동차", "바이오·제약", "의료기기", "미디어·콘텐츠", "AI·소프트웨어",
    "전자부품", "전력기기", "기계·산업장비", "환경·폐기물", "해운·물류",
    "항공·여행", "유통·소비", "교육", "레저", "철강·금속",
}

INDUSTRY_GROUP_HINTS: dict[str, str] = {
    "전자부품·컴퓨터": "전자부품",
    "전기장비": "전력기기",
    "자동차·부품": "자동차",
    "조선·운송장비": "조선",
    "제약": "바이오·제약",
    "의료·정밀기기": "의료기기",
    "소프트웨어·콘텐츠": "AI·소프트웨어",
    "IT서비스·시스템개발": "AI·소프트웨어",
    "정보서비스": "AI·소프트웨어",
    "영상·엔터테인먼트": "미디어·콘텐츠",
    "방송": "미디어·콘텐츠",
    "예술·콘텐츠": "미디어·콘텐츠",
    "통신": "통신",
    "금융": "금융",
    "금융지원": "금융",
    "보험": "보험",
    "건축": "건설",
    "건설·인프라": "건설",
    "건자재·비금속": "건자재",
    "식품": "음식료",
    "음료": "음식료",
    "의류": "의류·패션",
    "가죽·신발": "의류·패션",
    "철강·금속": "철강·금속",
    "기계·장비": "기계·산업장비",
    "산업장비 수리": "기계·산업장비",
    "폐기물·재활용": "환경·폐기물",
    "환경·하수처리": "환경·폐기물",
    "환경복원": "환경·폐기물",
    "해운": "해운·물류",
    "물류·창고": "해운·물류",
    "항공": "항공·여행",
    "소매·유통": "유통·소비",
    "도매": "유통·소비",
    "교육": "교육",
    "스포츠·레저": "레저",
    # Broad/ambiguous divisions intentionally remain hints only and are not
    # promoted by the safe-industry fallback (e.g. 화학, 연구개발, 전문서비스).
    "화학": "화학·소재",
}


def _norm(value: Any) -> str:
    value = str(value or "").casefold()
    value = value.replace("ㆍ", "·")
    value = re.sub(r"[\(\)\[\]{}<>_/,+|:;]", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def _contains(text: str, keyword: str) -> bool:
    t = _norm(text)
    k = _norm(keyword)
    if not t or not k:
        return False
    # Short latin tokens such as AI/EV must be token-bounded to avoid random
    # substring matches inside an English word.
    if re.fullmatch(r"[a-z0-9.+-]+", k) and len(k) <= 4:
        return re.search(rf"(?<![a-z0-9]){re.escape(k)}(?![a-z0-9])", t) is not None
    return k in t


def theme_alpha_key(value: Any) -> tuple[int, str]:
    text = str(value or "").strip()
    return (0 if re.search(r"[가-힣]", text) else 1, text.casefold())


def taxonomy_groups() -> list[str]:
    return sorted({rule.group for rule in THEME_RULES}, key=theme_alpha_key)


def taxonomy_tree() -> dict[str, list[str]]:
    tree: dict[str, set[str]] = defaultdict(set)
    for rule in THEME_RULES:
        if rule.subtheme and rule.subtheme != rule.group:
            tree[rule.group].add(rule.subtheme)
    return {group: sorted(values, key=theme_alpha_key) for group, values in sorted(tree.items(), key=lambda item: theme_alpha_key(item[0]))}


def map_theme_name(value: Any) -> list[dict[str, Any]]:
    """Map one provider/free-form theme label into the fixed hierarchy."""
    text = str(value or "").strip()
    if not text:
        return []
    matches: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for rule in THEME_RULES:
        matched_keyword = next((kw for kw in rule.keywords if _contains(text, kw)), None)
        if not matched_keyword:
            continue
        key = (rule.group, rule.subtheme)
        if key in seen:
            continue
        seen.add(key)
        exact = _norm(text) in {_norm(rule.group), _norm(rule.subtheme), *(_norm(k) for k in rule.keywords)}
        specificity = 2.0 if rule.subtheme != rule.group else 0.5
        if exact:
            specificity += 1.5
        matches.append({
            "group": rule.group,
            "subtheme": rule.subtheme,
            "keyword": matched_keyword,
            "specificity": specificity,
        })
    # Prefer specific children over the broad parent when both matched the same text.
    matches.sort(key=lambda item: (item["specificity"], len(item["subtheme"])), reverse=True)
    return matches


def canonical_group_for_theme(value: Any) -> str:
    matches = map_theme_name(value)
    return str(matches[0]["group"]) if matches else str(value or "").strip()


def _add_text_evidence(
    scores: dict[str, float],
    sub_scores: dict[tuple[str, str], float],
    sources: dict[str, set[str]],
    evidence: list[dict[str, Any]],
    text: str,
    *,
    source: str,
    weight: float,
) -> None:
    if not str(text or "").strip():
        return
    # One source should not count the same parent dozens of times because a news
    # sentence repeats similar words. Keep the strongest match per group.
    best_by_group: dict[str, dict[str, Any]] = {}
    for item in map_theme_name(text):
        current = best_by_group.get(item["group"])
        if current is None or float(item["specificity"]) > float(current["specificity"]):
            best_by_group[item["group"]] = item
    for group, item in best_by_group.items():
        points = weight * (1.0 + min(0.35, float(item["specificity"]) * 0.08))
        scores[group] += points
        sub_scores[(group, item["subtheme"])] += points
        sources[group].add(source)
        evidence.append({"source": source, "text": str(text)[:140], "group": group, "subtheme": item["subtheme"], "points": round(points, 2)})


def classify_stock_context(ctx: dict[str, Any]) -> dict[str, Any] | None:
    """Deterministically classify one stock into stable parent/sub themes."""
    name = str(ctx.get("name") or "").strip()
    override = COMPANY_OVERRIDES.get(name)
    if override:
        return {
            **override,
            "source_summary": "StockLog 표준 테마 사전 · 검증된 기업 예외규칙",
            "engine_version": THEME_ENGINE_VERSION,
            "evidence": [{"source": "verified_override", "group": override["theme_group"], "points": 100}],
        }

    scores: dict[str, float] = defaultdict(float)
    sub_scores: dict[tuple[str, str], float] = defaultdict(float)
    sources: dict[str, set[str]] = defaultdict(set)
    evidence: list[dict[str, Any]] = []

    # Provider membership is the strongest generic signal: the provider already
    # says the stock belongs to that market theme. Each raw label is normalized
    # through our taxonomy instead of being exposed verbatim.
    for raw in ctx.get("provider_themes") or []:
        _add_text_evidence(scores, sub_scores, sources, evidence, str(raw), source="provider_theme", weight=8.0)

    # Existing business text or detailed descriptions are more reliable than a
    # broad exchange industry label.
    _add_text_evidence(scores, sub_scores, sources, evidence, str(ctx.get("existing_business") or ""), source="business", weight=7.0)
    previous_theme=str(ctx.get("existing_investment_theme") or "").strip()
    previous_group=str(ctx.get("previous_theme_group") or "").strip()
    if previous_group:
        _add_text_evidence(scores, sub_scores, sources, evidence, previous_group, source="previous_theme_group", weight=4.1)
    if previous_theme and _norm(previous_theme) != _norm(previous_group):
        _add_text_evidence(scores, sub_scores, sources, evidence, previous_theme, source="previous_theme", weight=2.8)
    _add_text_evidence(scores, sub_scores, sources, evidence, str(ctx.get("legacy_primary_theme") or ""), source="legacy_primary_theme", weight=2.4)
    _add_text_evidence(scores, sub_scores, sources, evidence, str(ctx.get("sector") or ""), source="sector", weight=0.8)
    for alias in ctx.get("name_aliases") or []:
        _add_text_evidence(scores, sub_scores, sources, evidence, str(alias), source="company_alias", weight=1.2)
    _add_text_evidence(scores, sub_scores, sources, evidence, name, source="company_name", weight=2.5)

    for text in ctx.get("recent_reports") or []:
        _add_text_evidence(scores, sub_scores, sources, evidence, str(text), source="broker_report", weight=5.0)
    for text in ctx.get("recent_news") or []:
        _add_text_evidence(scores, sub_scores, sources, evidence, str(text), source="news", weight=2.2)

    industry = str(ctx.get("official_industry") or "").strip()
    hint = INDUSTRY_GROUP_HINTS.get(industry)
    if hint:
        scores[hint] += 0.8
        sources[hint].add("official_industry")
        evidence.append({"source": "official_industry", "text": industry, "group": hint, "points": 0.8})
    else:
        _add_text_evidence(scores, sub_scores, sources, evidence, industry, source="official_industry", weight=0.5)

    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    if not ranked:
        return None
    top_group, top_score = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else 0.0

    # A broad industry alone normally must not create an investor-facing theme.
    # A short allow-list is safe enough to use as a last-resort parent group
    # (e.g. 은행/보험/통신). Ambiguous buckets such as 화학/전자/기계 are excluded.
    official_only=(sources[top_group] == {"official_industry"})
    industry_fallback=False
    if official_only and top_group in SAFE_INDUSTRY_FALLBACK_GROUPS:
        # Last-resort standardization. This is deliberately lower-confidence
        # than provider/business evidence and is surfaced as an industry-assisted
        # classification rather than pretending the exchange industry is a theme.
        top_score=4.2
        industry_fallback=True
    elif top_score < 4.0 or official_only:
        return None

    # Multiple parent groups are kept when they have strong independent evidence.
    groups = [group for group, score in ranked if score >= max(5.0, top_score * 0.48)][:3]
    if top_group not in groups:
        groups.insert(0, top_group)

    subs = [
        (sub, score)
        for (group, sub), score in sub_scores.items()
        if group == top_group and sub != top_group and score >= max(3.0, top_score * 0.22)
    ]
    subs = [sub for sub, _score in sorted(subs, key=lambda item: item[1], reverse=True)][:6]

    source_count = len(sources[top_group])
    margin = max(0.0, top_score - second_score)
    if industry_fallback:
        confidence = 56
    else:
        confidence = 58 + min(24, int(top_score * 1.5)) + min(10, int(margin)) + min(8, source_count * 2)
        confidence = max(60, min(98, confidence))

    business = str(ctx.get("existing_business") or "").strip()
    if not business:
        business = f"{top_group} 관련 사업"
        if subs:
            business = f"{subs[0]} 중심 {top_group} 관련 사업"

    used_sources = sorted(sources[top_group])
    if industry_fallback:
        reason = (
            f"직접적인 투자테마 근거가 부족해 OpenDART 공식 업종 '{industry}'을 보조 근거로 "
            f"StockLog 상위 표준 테마 '{top_group}'에 임시 정규화했습니다. 강한 테마 근거가 새로 수집되면 자동으로 재분류됩니다."
        )
    else:
        reason = (
            f"공급사 테마·사업정보·리포트·뉴스를 StockLog 표준 테마 체계로 점수화한 결과 "
            f"'{top_group}' 근거가 가장 강했습니다. 공식 업종은 낮은 가중치의 참고값으로만 사용합니다."
        )
    return {
        "primary_business": business[:160],
        "theme_group": top_group,
        "theme_groups": groups,
        "subthemes": subs,
        "confidence": confidence,
        "reason": reason,
        "source_summary": ("StockLog Theme Engine · 업종 보조분류" if industry_fallback else ", ".join(used_sources) or "StockLog Theme Engine"),
        "classification_mode": "industry_fallback" if industry_fallback else "evidence",
        "engine_version": THEME_ENGINE_VERSION,
        "evidence": evidence[:40],
    }


def normalize_stored_theme_payload(
    group: Any,
    groups: Any,
    subthemes: Any,
) -> tuple[str, list[str], list[str]]:
    primary = str(group or "").strip()
    group_values: list[str] = []
    sub_values: list[str] = []
    if isinstance(groups, Iterable) and not isinstance(groups, (str, bytes, dict)):
        group_values = [str(x or "").strip() for x in groups if str(x or "").strip()]
    if isinstance(subthemes, Iterable) and not isinstance(subthemes, (str, bytes, dict)):
        sub_values = [str(x or "").strip() for x in subthemes if str(x or "").strip()]
    if primary and primary not in group_values:
        group_values.insert(0, primary)
    return primary, list(dict.fromkeys(group_values))[:3], list(dict.fromkeys(sub_values))[:8]
