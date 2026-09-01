import asyncio
import hashlib, html, io, os, re, zipfile
from difflib import SequenceMatcher
from email.utils import parsedate_to_datetime
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from urllib.parse import quote_plus, urlsplit, urlunsplit, urljoin, parse_qs

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import or_
from sqlalchemy.orm import Session

from .models import BrokerReportCache, DisclosureCache, FinancialQuarter, NewsCache, Stock
from .external_api import PROVIDER_DART, PROVIDER_NAVER, NAVER_API_HUB_NEWS_URL, naver_api_hub_headers, get_provider_credentials, tracked_get
from .db_utils import commit_or_rollback


# ---------------------------------------------------------
# Npay Finance / InfoStock actual domestic market themes
# ---------------------------------------------------------

NAVER_FINANCE_BASE = "https://finance.naver.com"
NAVER_THEME_LIST_URL = NAVER_FINANCE_BASE + "/sise/theme.naver"
NAVER_THEME_DETAIL_URL = NAVER_FINANCE_BASE + "/sise/sise_group_detail.naver"


def _decode_naver_finance(content: bytes):
    for enc in ("euc-kr", "cp949", "utf-8"):
        try:
            return content.decode(enc)
        except Exception:
            pass
    return content.decode("utf-8", errors="replace")


def _theme_no_from_href(href: str):
    q = parse_qs(urlsplit(urljoin(NAVER_FINANCE_BASE, href or "")).query)
    if str((q.get("type") or [""])[0]).lower() != "theme":
        return ""
    no = str((q.get("no") or [""])[0]).strip()
    return no if no.isdigit() else ""


def _stock_code_from_href(href: str):
    q = parse_qs(urlsplit(urljoin(NAVER_FINANCE_BASE, href or "")).query)
    code = str((q.get("code") or [""])[0]).strip()
    return code if re.fullmatch(r"\d{6}", code) else ""


def _parse_market_theme_catalog(html_text: str):
    soup = BeautifulSoup(html_text or "", "html.parser")
    out = {}

    for a in soup.select("a[href*='sise_group_detail.naver']"):
        no = _theme_no_from_href(a.get("href", ""))
        name = " ".join(a.stripped_strings).strip()
        if not no or not name:
            continue

        change_rate = None
        tr = a.find_parent("tr")
        if tr:
            m = re.search(
                r"([+-]?\d+(?:\.\d+)?)\s*%",
                " ".join(tr.stripped_strings),
            )
            if m:
                try:
                    change_rate = float(m.group(1))
                except Exception:
                    pass

        out[no] = {
            "theme_no": no,
            "theme_code": f"INFO:{no}",
            "theme_name": name,
            "change_rate": change_rate,
            "source": "infostock",
        }

    return list(out.values())


def _parse_market_theme_members(
    html_text: str,
    *,
    with_diagnostics: bool = False,
):
    """
    Parse the actual constituent-stock table from an Npay Finance theme page.

    Do not rely on a single CSS class. Npay's HTML layout can change while
    the semantic table headers remain stable. We identify a constituent
    table by:
      - stock item links, and
      - stock-table headers such as 종목명 / 현재가.

    Popular-search/news links outside that table are excluded.
    """
    soup = BeautifulSoup(
        html_text or "",
        "html.parser",
    )

    out = {}
    candidate_tables = []

    for table in soup.find_all("table"):
        text = " ".join(
            table.stripped_strings
        )

        stock_links = [
            a
            for a in table.find_all(
                "a",
                href=True,
            )
            if _stock_code_from_href(
                a.get("href", "")
            )
        ]

        if not stock_links:
            continue

        header_score = sum(
            1
            for keyword in (
                "종목명",
                "현재가",
                "등락률",
                "거래량",
            )
            if keyword in text
        )

        # The real theme constituent table contains stock links and multiple
        # stock-market column labels. Requiring >=2 protects against sidebar
        # or popular-search tables.
        if header_score >= 2:
            candidate_tables.append(
                (
                    header_score,
                    table,
                    stock_links,
                )
            )

    # Highest semantic score first. In normal Npay pages this is one table.
    candidate_tables.sort(
        key=lambda x: x[0],
        reverse=True,
    )

    for _, table, stock_links in candidate_tables:
        for a in stock_links:
            code = _stock_code_from_href(
                a.get("href", "")
            )
            if not code:
                continue

            name = " ".join(
                a.stripped_strings
            ).strip()

            if not name:
                continue

            out[code] = {
                "code": code,
                "name": name,
            }

        if out:
            break

    diagnostics = {
        "candidate_tables":
            len(candidate_tables),
        "all_tables":
            len(
                soup.find_all("table")
            ),
        "all_stock_links":
            len(
                [
                    a
                    for a in soup.find_all(
                        "a",
                        href=True,
                    )
                    if _stock_code_from_href(
                        a.get("href", "")
                    )
                ]
            ),
        "member_count":
            len(out),
        "page_title":
            (
                soup.title.get_text(
                    " ",
                    strip=True,
                )
                if soup.title
                else ""
            ),
    }

    if with_diagnostics:
        return (
            list(out.values()),
            diagnostics,
        )

    return list(
        out.values()
    )


class NaverInfoStockThemeClient:
    """
    Reads actual theme names and constituent stock codes shown on Npay Finance.
    The page identifies InfoStock as its domestic theme-information provider.
    StockLog stores only theme names and membership, not descriptive/reason text.
    """

    def __init__(self, timeout_seconds=12.0, request_gap_seconds=0.12):
        self.timeout_seconds = float(timeout_seconds)
        self.request_gap_seconds = float(request_gap_seconds)
        self.client = None
        self.last_catalog_pages = 0

    async def __aenter__(self):
        self.client = httpx.AsyncClient(
            timeout=self.timeout_seconds,
            follow_redirects=True,
            headers={
                "User-Agent":
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/150.0.0.0 Safari/537.36",
                "Accept":
                    "text/html,application/xhtml+xml,application/xml;"
                    "q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language":
                    "ko-KR,ko;q=0.9,en-US;q=0.7,en;q=0.6",
                "Cache-Control":
                    "no-cache",
                "Referer":
                    NAVER_THEME_LIST_URL,
            },
        )
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if self.client:
            await self.client.aclose()
            self.client = None

    async def _get(self, url, params=None):
        if not self.client:
            raise RuntimeError("NaverInfoStockThemeClient must be used with async with")

        last = None
        for attempt in range(1, 4):
            try:
                r = await self.client.get(url, params=params)
                if r.status_code == 429:
                    await asyncio.sleep(0.75 * attempt)
                    continue
                r.raise_for_status()

                text = _decode_naver_finance(
                    r.content
                )

                lowered = text.lower()

                if (
                    "접근이 제한" in text
                    or "비정상적인 접근" in text
                    or "service unavailable" in lowered
                ):
                    raise RuntimeError(
                        "Npay 증권에서 접근 제한 응답을 반환했습니다."
                    )

                if len(text.strip()) < 500:
                    raise RuntimeError(
                        "Npay 증권 HTML 응답이 비정상적으로 짧습니다 "
                        f"({len(text):,} bytes)."
                    )

                if self.request_gap_seconds:
                    await asyncio.sleep(
                        self.request_gap_seconds
                    )

                return text
            except Exception as exc:
                last = exc
                if attempt < 3:
                    await asyncio.sleep(0.5 * attempt)

        raise RuntimeError(
            f"Npay 증권 시장 테마 조회 실패: {type(last).__name__}: {last}"
        )

    async def catalog(self, progress_cb=None, max_pages=30):
        found = {}
        pages = 0

        for page in range(1, max_pages + 1):
            if progress_cb:
                result = progress_cb({
                    "status": "catalog_request",
                    "page": page,
                    "message": f"시장 테마 목록 {page}페이지 조회 중",
                })
                if hasattr(result, "__await__"):
                    await result

            html_text = await self._get(
                NAVER_THEME_LIST_URL,
                params={"page": page},
            )
            items = _parse_market_theme_catalog(html_text)
            new_count = 0

            for item in items:
                if item["theme_no"] not in found:
                    new_count += 1
                found[item["theme_no"]] = item

            if not items or new_count == 0:
                break

            pages = page

            if progress_cb:
                result = progress_cb({
                    "status": "catalog_page_done",
                    "page": page,
                    "theme_count": len(found),
                    "message": f"시장 테마 {len(found):,}개 확인",
                })
                if hasattr(result, "__await__"):
                    await result

        self.last_catalog_pages = pages
        return list(found.values())

    async def members(self, theme_no: str):
        theme_no = str(
            theme_no or ""
        ).strip()

        if not theme_no.isdigit():
            raise ValueError(
                "시장 테마 번호가 올바르지 않습니다."
            )

        html_text = await self._get(
            NAVER_THEME_DETAIL_URL,
            params={
                "no":
                    theme_no,
                "type":
                    "theme",
            },
        )

        members, diagnostics = (
            _parse_market_theme_members(
                html_text,
                with_diagnostics=True,
            )
        )

        if not members:
            raise RuntimeError(
                "시장 테마 구성종목 파싱 결과가 0건입니다. "
                f"theme_no={theme_no}, "
                f"candidate_tables={diagnostics['candidate_tables']}, "
                f"all_stock_links={diagnostics['all_stock_links']}, "
                f"title={diagnostics['page_title']!r}"
            )

        return (
            members,
            diagnostics,
        )


# ---------------------------------------------------------
# Google News RSS + Korean stock sentiment
# ---------------------------------------------------------

# 단순 단어 개수만 세지 않고, 주식 뉴스에서 방향성이 강한 표현에 가중치를 줍니다.
POSITIVE_PHRASES = {
    "상한가": 3.5,
    "흑자전환": 3.2,
    "사상 최대": 3.0,
    "역대 최대": 3.0,
    "어닝 서프라이즈": 3.0,
    "실적 호조": 2.5,
    "호실적": 2.5,
    "목표가 상향": 2.5,
    "목표주가 상향": 2.5,
    "수주": 2.0,
    "계약 체결": 2.0,
    "공급 계약": 2.0,
    "신고가": 2.0,
    "강세": 1.7,
    "급등": 1.7,
    "상승": 1.2,
    "증가": 1.0,
    "성장": 1.2,
    "개선": 1.2,
    "확대": 1.0,
    "회복": 1.2,
    "돌파": 1.2,
    "상향": 1.0,
    "기대": 0.8,
    "턴어라운드": 2.0,
    "적자 축소": 2.2,
    "우려 해소": 2.2,
}

NEGATIVE_PHRASES = {
    "하한가": 3.5,
    "적자전환": 3.2,
    "어닝 쇼크": 3.0,
    "실적 쇼크": 3.0,
    "상장폐지": 3.5,
    "거래정지": 3.0,
    "횡령": 3.0,
    "배임": 3.0,
    "목표가 하향": 2.5,
    "목표주가 하향": 2.5,
    "실적 부진": 2.4,
    "급락": 2.2,
    "약세": 1.7,
    "하락": 1.2,
    "감소": 1.0,
    "적자": 1.5,
    "손실": 1.5,
    "부진": 1.4,
    "둔화": 1.3,
    "우려": 1.0,
    "리스크": 1.2,
    "소송": 1.5,
    "하향": 1.0,
    "감산": 1.2,
    "유상증자": 0.9,
}

NEWS_RSS_URL = "https://news.google.com/rss/search"


def strip_html(text):
    return re.sub(r"<[^>]+>", "", html.unescape(text or "")).strip()


def _canonical_url(url):
    url = (url or "").strip()
    try:
        p = urlsplit(url)
        return urlunsplit(
            (
                p.scheme.lower(),
                p.netloc.lower(),
                p.path.rstrip("/"),
                p.query,
                "",
            )
        )
    except Exception:
        return url


def _news_key(stock_code, link, title):
    raw = (
        f"{stock_code}|"
        f"{_canonical_url(link) or strip_html(title).lower()}"
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _parse_pubdate(text):
    if not text:
        return None
    raw=str(text).strip()
    try:
        dt=parsedate_to_datetime(raw)
        if dt:
            return dt.astimezone().replace(tzinfo=None) if dt.tzinfo else dt
    except Exception:
        pass
    for fmt in (
        "%Y-%m-%d %H:%M", "%Y-%m-%d", "%Y.%m.%d", "%Y%m%d",
        "%a, %d %b %Y %H:%M:%S %Z", "%a, %d %b %Y %H:%M:%S %z",
    ):
        try:
            dt=datetime.strptime(raw,fmt)
            return dt.replace(tzinfo=None)
        except Exception:
            pass
    return None

def _display_pubdate(text):
    dt = _parse_pubdate(text)
    if not dt:
        return text or ""
    return dt.strftime("%Y-%m-%d %H:%M")


def analyze_news_sentiment(title, description=""):
    """
    주식 뉴스 방향성 분석.
    - 제목을 본문 요약보다 2배 강하게 반영
    - 강한 금융 표현은 높은 가중치
    - 결과: positive / neutral / negative
    - 점수: -1.0 ~ +1.0
    """
    title = strip_html(title)
    description = strip_html(description)

    positive_hits = []
    negative_hits = []
    positive_score = 0.0
    negative_score = 0.0

    for phrase, weight in POSITIVE_PHRASES.items():
        title_count = title.count(phrase)
        desc_count = description.count(phrase)

        if title_count or desc_count:
            score = title_count * weight * 2.0 + desc_count * weight
            positive_score += score
            positive_hits.append((phrase, score))

    for phrase, weight in NEGATIVE_PHRASES.items():
        title_count = title.count(phrase)
        desc_count = description.count(phrase)

        if title_count or desc_count:
            score = title_count * weight * 2.0 + desc_count * weight
            negative_score += score
            negative_hits.append((phrase, score))

    # 문맥상 긍정 의미가 강한 복합표현이 단순 부정단어를 상쇄하도록 보정
    if "적자 축소" in f"{title} {description}":
        negative_score = max(0, negative_score - 1.5)

    if "우려 해소" in f"{title} {description}":
        negative_score = max(0, negative_score - 1.0)

    total = positive_score + negative_score

    if total <= 0:
        return {
            "label": "neutral",
            "score": 0.0,
            "reason": "명확한 긍정/부정 방향성 표현이 적음",
            "positive_keywords": [],
            "negative_keywords": [],
        }

    raw = (positive_score - negative_score) / max(total, 1.0)
    score = max(-1.0, min(1.0, raw))

    if score >= 0.18:
        label = "positive"
    elif score <= -0.18:
        label = "negative"
    else:
        label = "neutral"

    positive_hits.sort(key=lambda x: x[1], reverse=True)
    negative_hits.sort(key=lambda x: x[1], reverse=True)

    pos_words = [x[0] for x in positive_hits[:4]]
    neg_words = [x[0] for x in negative_hits[:4]]

    if label == "positive":
        reason = (
            "긍정 키워드: " + ", ".join(pos_words)
            if pos_words
            else "긍정 방향성이 우세"
        )
    elif label == "negative":
        reason = (
            "부정 키워드: " + ", ".join(neg_words)
            if neg_words
            else "부정 방향성이 우세"
        )
    else:
        reason_parts = []
        if pos_words:
            reason_parts.append("긍정 " + ", ".join(pos_words[:2]))
        if neg_words:
            reason_parts.append("부정 " + ", ".join(neg_words[:2]))
        reason = (
            " / ".join(reason_parts)
            if reason_parts
            else "긍정/부정 신호가 혼재"
        )

    return {
        "label": label,
        "score": round(score, 3),
        "reason": reason,
        "positive_keywords": pos_words,
        "negative_keywords": neg_words,
    }


def _direction_brief(sentiment):
    positive=list(sentiment.get("positive_keywords") or [])
    negative=list(sentiment.get("negative_keywords") or [])
    label=sentiment.get("label") or "neutral"
    if label=="positive":
        return (f"{', '.join(positive[:3])} 관련 긍정 표현이 핵심입니다." if positive else "기사 제목/요약에서 긍정 방향의 표현이 우세합니다.")
    if label=="negative":
        return (f"{', '.join(negative[:3])} 관련 부정 표현이 핵심입니다." if negative else "기사 제목/요약에서 부정 방향의 표현이 우세합니다.")
    parts=[]
    if positive: parts.append("긍정 "+", ".join(positive[:2]))
    if negative: parts.append("부정 "+", ".join(negative[:2]))
    return (" / ".join(parts)+" 신호가 함께 나타납니다." if parts else "뚜렷한 긍정/부정 금융 표현이 적어 관망으로 분류했습니다.")


def _news_item_analysis(item):
    sent=analyze_news_sentiment(item.get("title") or "",item.get("description") or "")
    return {**item,"sentiment":sent["label"],"sentiment_score":sent["score"],"sentiment_reason":sent["reason"],"positive_keywords":sent["positive_keywords"],"negative_keywords":sent["negative_keywords"],"brief_summary":_direction_brief(sent)}


def _keyword_frequency(items,key):
    freq={}
    for item in items:
        for word in item.get(key) or []:
            word=str(word or "").strip()
            if word: freq[word]=freq.get(word,0)+1
    return [word for word,_ in sorted(freq.items(),key=lambda x:(-x[1],x[0]))]


def _news_summary(items):
    analyzed=[_news_item_analysis(item) for item in (items or []) if isinstance(item,dict)]
    counts={"positive":0,"neutral":0,"negative":0}
    scores=[]
    for item in analyzed:
        label=item.get("sentiment","neutral")
        if label not in counts: label="neutral"
        counts[label]+=1
        scores.append(float(item.get("sentiment_score") or 0))
    avg=sum(scores)/len(scores) if scores else 0.0
    overall="positive" if avg>=.15 else "negative" if avg<=-.15 else "neutral"
    pos_kw=_keyword_frequency(analyzed,"positive_keywords")[:5]
    neg_kw=_keyword_frequency(analyzed,"negative_keywords")[:5]
    pos_points=[{"title":x.get("title") or "","publisher":x.get("publisher") or "","summary":x.get("brief_summary") or "","score":x.get("sentiment_score") or 0} for x in analyzed if x.get("sentiment")=="positive"][:3]
    neg_points=[{"title":x.get("title") or "","publisher":x.get("publisher") or "","summary":x.get("brief_summary") or "","score":x.get("sentiment_score") or 0} for x in analyzed if x.get("sentiment")=="negative"][:3]
    comment={"positive":"최근 뉴스는 긍정 신호가 우세합니다.","negative":"최근 뉴스는 부정 신호가 우세해 위험 요인 확인이 필요합니다.","neutral":"최근 뉴스는 긍정/부정 신호가 혼재하거나 방향성이 약합니다."}[overall]
    parts=[]
    if pos_kw: parts.append("긍정: "+", ".join(pos_kw[:3]))
    if neg_kw: parts.append("부정: "+", ".join(neg_kw[:3]))
    if parts: comment += " " + " / ".join(parts)
    return {"overall":overall,"average_score":round(avg,3),"total":len(analyzed),"positive_keywords":pos_kw,"negative_keywords":neg_kw,"positive_points":pos_points,"negative_points":neg_points,"overall_comment":comment,**counts}

def _news_json(row):
    item={
        "title":row.title,
        "description":row.description or "",
        "link":row.link,
        "publisher":row.publisher or "",
        "published_at":row.published_dt.strftime("%Y-%m-%d %H:%M") if getattr(row,"published_dt",None) else (row.published_at or ""),
        "published_dt":row.published_dt.isoformat() if getattr(row,"published_dt",None) else None,
        "source":getattr(row,"source","") or "",
        "relevance_score":round(float(getattr(row,"relevance_score",0) or 0),1),
        "importance_score":round(float(getattr(row,"importance_score",0) or 0),1),
        "importance_reason":getattr(row,"importance_reason","") or "",
        "sentiment":row.sentiment,
        "sentiment_score":row.sentiment_score,
        "sentiment_reason":row.sentiment_reason or "",
        "fetched_at":row.fetched_at.isoformat() if row.fetched_at else None,
    }
    return _news_item_analysis(item)


def _normalize_news_title(title):
    value=strip_html(title).lower()
    value=re.sub(r"\[[^\]]+\]|\([^\)]*기자[^\)]*\)"," ",value)
    value=re.sub(r"[^0-9a-z가-힣]+"," ",value)
    return " ".join(value.split())


def _news_source_quality(publisher,link):
    text=f"{publisher or ''} {link or ''}".lower()
    # This is intentionally a small reliability prior, not a political/editorial rating.
    high=("연합뉴스","yna.co.kr","한국거래소","krx","금융감독원","fss.or.kr","전자신문","etnews","매일경제","mk.co.kr","한국경제","hankyung","서울경제","sedaily","머니투데이","mt.co.kr","조선비즈","chosunbiz","이데일리","edaily")
    medium=("뉴스1","news1","뉴시스","newsis","파이낸셜뉴스","fnnews","아시아경제","asiae","헤럴드경제","heraldcorp")
    if any(x.lower() in text for x in high): return 100.0
    if any(x.lower() in text for x in medium): return 85.0
    return 70.0


def _news_relevance(stock,title,description,query=""):
    title=strip_html(title); description=strip_html(description)
    combined=f"{title} {description}"
    name=(stock.name or "").strip()
    score=0.0; reasons=[]
    if name and name in title:
        score+=70; reasons.append("종목명이 제목에 직접 포함")
    elif name and name in description:
        score+=48; reasons.append("종목명이 기사 요약에 포함")
    if stock.code and stock.code in combined:
        score+=18; reasons.append("종목코드 포함")
    finance_words=("주가","주식","증권","실적","매출","영업이익","순이익","목표주가","투자의견","수주","계약","공시","배당","증자","인수","합병","반도체","판매","출하","투자")
    hits=sum(1 for w in finance_words if w in combined)
    score+=min(20,hits*4)
    # Query-only matches should never outrank a direct company mention.
    if query and any(x in combined for x in str(query).split() if len(x)>=2): score+=3
    if len(name)<=2 and name not in combined: score-=60
    return max(0.0,min(100.0,score)), ", ".join(reasons[:2])


def _news_importance(stock,title,description,published_dt,publisher,link,relevance):
    combined=f"{strip_html(title)} {strip_html(description)}"
    impact={
        "잠정실적":28,"실적":16,"영업이익":14,"매출":9,"순이익":10,
        "공시":18,"단일판매":24,"공급계약":24,"수주":22,"계약 체결":18,
        "유상증자":28,"무상증자":18,"자사주":17,"배당":15,
        "합병":25,"분할":24,"인수":19,"매각":18,"최대주주":18,
        "소송":24,"횡령":30,"배임":30,"거래정지":30,"상장폐지":35,
        "목표주가":10,"투자의견":10,"상향":10,"하향":12,
        "정부":7,"승인":10,"허가":10,"임상":13,"리콜":20,
    }
    event=0.0; matched=[]
    for word,weight in impact.items():
        if word in combined:
            event=max(event,float(weight)); matched.append(word)
    if published_dt:
        age_h=max(0,(datetime.now()-published_dt).total_seconds()/3600)
        if age_h<=6: recency=100
        elif age_h<=24: recency=92
        elif age_h<=72: recency=80
        elif age_h<=168: recency=65
        elif age_h<=720: recency=45
        else: recency=20
    else: recency=20
    quality=_news_source_quality(publisher,link)
    # relevance is deliberately dominant so generic market articles do not pollute AI context.
    score=0.38*relevance+0.27*recency+0.20*min(100,event*3)+0.15*quality
    reason=[]
    if matched: reason.append("핵심 이벤트: "+", ".join(matched[:3]))
    if recency>=90: reason.append("최근 24시간")
    if relevance>=80: reason.append("종목 직접 관련")
    return round(max(0,min(100,score)),1), " · ".join(reason) or "관련성·최신성 기준"


def _google_rss_queries(stock):
    name=(stock.name or "").strip()
    return [
        f'"{name}" 주식',
        f'"{name}" 실적 OR 영업이익',
        f'"{name}" 공시 OR 계약 OR 수주',
        f'"{name}" 전망 OR 목표주가',
    ]


def _parse_google_news_rss(xml_bytes,stock,source_query=""):
    root=ET.fromstring(xml_bytes); items=[]
    for node in root.findall(".//item"):
        title=strip_html(node.findtext("title") or "")
        link=(node.findtext("link") or "").strip()
        description=strip_html(node.findtext("description") or "")
        raw=(node.findtext("pubDate") or "").strip()
        source_node=node.find("source")
        publisher=strip_html(source_node.text or "") if source_node is not None else ""
        if not title or not link: continue
        if publisher and title.endswith(f" - {publisher}"): title=title[:-(len(publisher)+3)].strip()
        pdt=_parse_pubdate(raw)
        relevance,_=_news_relevance(stock,title,description,source_query)
        if relevance<45: continue
        importance,reason=_news_importance(stock,title,description,pdt,publisher,link,relevance)
        sent=analyze_news_sentiment(title,description)
        items.append({"title":title,"description":description,"link":link,"publisher":publisher,"published_at":_display_pubdate(raw),"published_dt":pdt,"sentiment":sent["label"],"sentiment_score":sent["score"],"sentiment_reason":sent["reason"],"dedupe_key":_news_key(stock.code,link,title),"source":"google-news-rss","source_query":source_query,"relevance_score":relevance,"importance_score":importance,"importance_reason":reason})
    return items


async def _fetch_google_news_multi(stock,client):
    async def one(query):
        r=await client.get(NEWS_RSS_URL,params={"q":query,"hl":"ko","gl":"KR","ceid":"KR:ko"})
        r.raise_for_status()
        return _parse_google_news_rss(r.content,stock,query)
    results=await asyncio.gather(*(one(q) for q in _google_rss_queries(stock)),return_exceptions=True)
    items=[]; errors=[]
    for result in results:
        if isinstance(result,Exception): errors.append(str(result))
        else: items.extend(result)
    return items,errors


async def _fetch_naver_news_multi(stock,client,db=None,request_kind="interactive"):
    creds=get_provider_credentials(PROVIDER_NAVER,db)
    client_id=(creds.get("client_id") or "").strip()
    client_secret=(creds.get("client_secret") or "").strip()
    if not client_id or not client_secret: return [],[]
    queries=[stock.name,f"{stock.name} 실적",f"{stock.name} 공시",f"{stock.name} 전망"]
    headers=naver_api_hub_headers(client_id,client_secret)
    async def one(query):
        r=await tracked_get(client,PROVIDER_NAVER,"search/news",NAVER_API_HUB_NEWS_URL,request_kind=request_kind,stock_code=stock.code,params={"query":query,"display":100,"start":1,"sort":"date"},headers=headers)
        r.raise_for_status(); data=r.json(); out=[]
        for raw in data.get("items") or []:
            title=strip_html(raw.get("title") or ""); desc=strip_html(raw.get("description") or "")
            link=(raw.get("originallink") or raw.get("link") or "").strip()
            if not title or not link: continue
            pdt=_parse_pubdate(raw.get("pubDate") or "")
            publisher=urlsplit(link).netloc.replace("www.","")
            relevance,_=_news_relevance(stock,title,desc,query)
            if relevance<45: continue
            importance,reason=_news_importance(stock,title,desc,pdt,publisher,link,relevance)
            sent=analyze_news_sentiment(title,desc)
            out.append({"title":title,"description":desc,"link":link,"publisher":publisher,"published_at":pdt.strftime("%Y-%m-%d %H:%M") if pdt else "","published_dt":pdt,"sentiment":sent["label"],"sentiment_score":sent["score"],"sentiment_reason":sent["reason"],"dedupe_key":_news_key(stock.code,link,title),"source":"naver-search-api","source_query":query,"relevance_score":relevance,"importance_score":importance,"importance_reason":reason})
        return out
    results=await asyncio.gather(*(one(q) for q in queries),return_exceptions=True)
    items=[]; errors=[]
    for result in results:
        if isinstance(result,Exception): errors.append(str(result))
        else: items.extend(result)
    return items,errors


def _dedupe_news_items(items):
    # URL exact duplicate first, then near-identical syndicated headlines.
    by_url={}; no_url=[]
    for item in items:
        key=_canonical_url(item.get("link") or "")
        if key:
            prev=by_url.get(key)
            if prev is None or float(item.get("importance_score") or 0)>float(prev.get("importance_score") or 0): by_url[key]=item
        else:no_url.append(item)
    ordered=sorted(list(by_url.values())+no_url,key=lambda x:(x.get("published_dt") or datetime.min,float(x.get("importance_score") or 0)),reverse=True)
    kept=[]
    for item in ordered:
        norm=_normalize_news_title(item.get("title") or "")
        duplicate=False
        for old in kept[-80:]:
            onorm=_normalize_news_title(old.get("title") or "")
            if norm and onorm and SequenceMatcher(None,norm,onorm).ratio()>=0.90:
                duplicate=True; break
        if not duplicate: kept.append(item)
    return kept


async def get_stock_news(stock:Stock,db:Session,force=False,ttl_seconds=None,display=20):
    """Multi-source, publication-date-first news pipeline for StockLog v3.39."""
    ttl_seconds=ttl_seconds or int(os.getenv("NEWS_CACHE_SECONDS","900"))
    display=max(1,min(int(display),50))
    cutoff=datetime.now()-timedelta(days=183)
    cached=(db.query(NewsCache).filter(NewsCache.stock_code==stock.code,NewsCache.published_dt>=cutoff).order_by(NewsCache.published_dt.desc(),NewsCache.id.desc()).limit(300).all())
    latest_fetch=max((x.fetched_at for x in cached if x.fetched_at),default=None)
    has_modern_cache=any(getattr(x,"published_dt",None) for x in cached)
    if not force and has_modern_cache and latest_fetch and datetime.now()-latest_fetch<timedelta(seconds=ttl_seconds):
        items=[_news_json(x) for x in cached[:display]]
        important=sorted(items,key=lambda x:float(x.get("importance_score") or 0),reverse=True)[:min(10,len(items))]
        return {"items":items,"important_items":important,"summary":_news_summary(items),"source":"mysql-market-intelligence-cache","fetched":False,"last_fetched_at":latest_fetch.isoformat()}

    headers={"User-Agent":"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/150.0 Safari/537.36 StockLog/3.39"}
    normalized=[]; errors=[]
    # Cached-news SELECTs above are finished. External search can take many
    # seconds, so return the request session's connection first and let the
    # NAVER credential lookup use its own short-lived session.
    commit_or_rollback(db)
    async with httpx.AsyncClient(timeout=18,follow_redirects=True,headers=headers) as client:
        request_kind="manual" if force else "interactive"
        nav_task=asyncio.create_task(_fetch_naver_news_multi(stock,client,None,request_kind))
        google_task=asyncio.create_task(_fetch_google_news_multi(stock,client))
        for result in await asyncio.gather(nav_task,google_task,return_exceptions=True):
            if isinstance(result,Exception): errors.append(str(result)); continue
            rows,errs=result; normalized.extend(rows); errors.extend(errs)
    normalized=_dedupe_news_items(normalized)
    normalized=[x for x in normalized if x.get("published_dt") and x.get("published_dt")>=cutoff]
    now=datetime.now(); inserted=updated=0
    keys=[x["dedupe_key"] for x in normalized]
    existing={r.dedupe_key:r for r in db.query(NewsCache).filter(NewsCache.stock_code==stock.code,NewsCache.dedupe_key.in_(keys)).all()} if keys else {}
    for item in normalized:
        row=existing.get(item["dedupe_key"])
        if not row:
            row=NewsCache(stock_code=stock.code,dedupe_key=item["dedupe_key"]); db.add(row); inserted+=1
        else: updated+=1
        row.title=item["title"]; row.description=item["description"]; row.link=item["link"]; row.publisher=item["publisher"]
        row.published_at=item["published_at"]; row.published_dt=item.get("published_dt"); row.source=item.get("source",""); row.source_query=item.get("source_query","")
        row.relevance_score=item.get("relevance_score",0); row.importance_score=item.get("importance_score",0); row.importance_reason=item.get("importance_reason","")
        row.sentiment=item["sentiment"]; row.sentiment_score=item["sentiment_score"]; row.sentiment_reason=item["sentiment_reason"]; row.fetched_at=now
    commit_or_rollback(db)
    rows=(db.query(NewsCache).filter(NewsCache.stock_code==stock.code,NewsCache.published_dt>=cutoff).order_by(NewsCache.published_dt.desc(),NewsCache.id.desc()).limit(display).all())
    items=[_news_json(x) for x in rows]
    important=sorted(items,key=lambda x:(float(x.get("importance_score") or 0),x.get("published_dt") or ""),reverse=True)[:min(10,len(items))]
    sources=sorted(set(x.get("source") or "" for x in normalized if x.get("source")))
    warning=None
    if errors and not normalized: warning="최신 뉴스 외부 조회 실패: "+" | ".join(errors[:2])
    elif errors: warning="일부 뉴스 소스 조회 실패(다른 소스 결과 사용): "+" | ".join(errors[:1])
    return {"items":items,"important_items":important,"summary":_news_summary(items),"source":"+".join(sources) or "mysql-market-intelligence-cache","fetched":True,"inserted":inserted,"updated":updated,"last_fetched_at":now.isoformat(),"warning":warning}


NAVER_RESEARCH_URL = "https://finance.naver.com/research/company_list.naver"


def _parse_naver_reports(html_text: str, stock: Stock, limit: int = 5):
    soup = BeautifulSoup(html_text, "html.parser")
    reports = []
    seen = set()

    for tr in soup.select("table.type_1 tr"):
        cols = tr.find_all("td")
        if len(cols) < 5:
            continue

        company = strip_html(cols[0].get_text(" ", strip=True))
        title_a = cols[1].find("a")
        title = strip_html(cols[1].get_text(" ", strip=True))
        broker = strip_html(cols[2].get_text(" ", strip=True))
        date_text = strip_html(cols[4].get_text(" ", strip=True))

        if not title_a or not title:
            continue

        # 검색 파라미터가 동작하지 않는 환경에 대비한 2차 필터
        if company and stock.name not in company and company not in stock.name:
            continue

        raw_href = title_a.get("href", "")
        href = urljoin(
            "https://finance.naver.com/research/",
            raw_href,
        )

        # 현재 네이버 금융 종목분석 상세의 정상 경로는
        # /research/company_read.naver 입니다.
        # 구형/상대 href가 /company_read.naver 로 들어와도 강제로 보정합니다.
        if "/company_read.naver" in href and "/research/company_read.naver" not in href:
            href = href.replace(
                "https://finance.naver.com/company_read.naver",
                "https://finance.naver.com/research/company_read.naver",
                1,
            )

        # 상세 페이지에서 목록 검색 문맥을 유지할 수 있도록 itemCode 파라미터를 보강합니다.
        if "company_read.naver" in href and "itemCode=" not in href:
            sep = "&" if "?" in href else "?"
            href = (
                f"{href}{sep}searchType=itemCode&itemCode={stock.code}"
            )

        key = (title, broker, date_text)
        if key in seen:
            continue
        seen.add(key)

        reports.append({
            "company": company or stock.name,
            "title": title,
            "broker": broker,
            "date": date_text,
            "link": href,
            "source": "Naver Finance Research",
        })

        if len(reports) >= limit:
            break

    return reports


def _report_opinion(text):
    cleaned=" ".join(str(text or "").split())
    patterns=[r"투자의견\s*[:：]?\s*(Trading\s*Buy|Strong\s*Buy|Outperform|Marketperform|Underperform|BUY|HOLD|SELL|매수|중립|보유|매도)",r"의견\s*[:：]?\s*(Trading\s*Buy|Strong\s*Buy|Outperform|Marketperform|Underperform|BUY|HOLD|SELL|매수|중립|보유|매도)"]
    for pattern in patterns:
        m=re.search(pattern,cleaned,re.I)
        if m: return " ".join(m.group(1).split())
    return ""


def _report_target_price(text):
    m=re.search(r"(?:목표주가|목표가|적정주가)\s*[:：]?\s*([0-9][0-9,]{2,})\s*원?"," ".join(str(text or "").split()),re.I)
    if not m:return None
    try:return int(m.group(1).replace(",",""))
    except:return None


def _extract_report_context(html_text):
    soup=BeautifulSoup(html_text or "","html.parser")
    for node in soup(["script","style","nav","header","footer"]): node.decompose()
    parts=[]
    for selector in ["#content",".view",".research_info",".box_type_m","table.type_1","table.view"]:
        for node in soup.select(selector):
            t=" ".join(node.stripped_strings)
            if len(t)>=20: parts.append(t)
    if not parts and soup.body: parts.append(" ".join(soup.body.stripped_strings))
    return " ".join(parts)[:6000]


def _report_analysis(title,context):
    context=strip_html(context or "")
    sent=analyze_news_sentiment(title,context)
    opinion=_report_opinion(f"{title} {context}")
    target=_report_target_price(f"{title} {context}")
    score=float(sent.get("score") or 0)
    ol=opinion.lower()
    if "buy" in ol or "outperform" in ol or "매수" in opinion: score=min(1.0,score+.25)
    elif "sell" in ol or "underperform" in ol or "매도" in opinion: score=max(-1.0,score-.35)
    label="positive" if score>=.18 else "negative" if score<=-.18 else "neutral"
    pos=list(sent.get("positive_keywords") or []); neg=list(sent.get("negative_keywords") or [])
    pos_points=[]; neg_points=[]
    if opinion:
        if label=="positive":pos_points.append(f"투자의견 {opinion}")
        elif label=="negative":neg_points.append(f"투자의견 {opinion}")
    if pos:pos_points.append("긍정 표현: "+", ".join(pos[:3]))
    if neg:neg_points.append("부정 표현: "+", ".join(neg[:3]))
    if target:
        text=f"공개 페이지에서 목표주가 {target:,}원 표현 확인"
        (neg_points if label=="negative" else pos_points).append(text)
    if label=="positive": brief="긍정 관점이 우세합니다. "+(" · ".join(pos_points[:2]) if pos_points else _direction_brief(sent))
    elif label=="negative": brief="부정 관점이 우세합니다. "+(" · ".join(neg_points[:2]) if neg_points else _direction_brief(sent))
    else:
        mixed=[]
        if pos_points:mixed.append(pos_points[0])
        if neg_points:mixed.append(neg_points[0])
        brief="관망 또는 혼재 관점입니다."+(" "+" / ".join(mixed) if mixed else " 제목·공개 페이지에서 강한 방향성 표현이 적습니다.")
    return {"sentiment":label,"sentiment_score":round(score,3),"sentiment_reason":sent.get("reason") or "","brief_summary":brief,"positive_points":pos_points[:3],"negative_points":neg_points[:3],"investment_opinion":opinion,"target_price":target}


async def _enrich_broker_report_item(client,item):
    enriched=dict(item);context=""
    try:
        r=await client.get(item.get("link") or "");r.raise_for_status()
        context=_extract_report_context(_decode_naver_finance(r.content))
        enriched["analysis_basis"]="리포트 제목 + 공개 상세페이지" if context else "리포트 제목"
    except Exception:
        enriched["analysis_basis"]="리포트 제목"
    enriched.update(_report_analysis(item.get("title") or "",context))
    return enriched


def _report_summary(items):
    counts={"positive":0,"neutral":0,"negative":0};scores=[];pos=[];neg=[]
    for item in items or []:
        label=item.get("sentiment","neutral")
        if label not in counts:label="neutral"
        counts[label]+=1;scores.append(float(item.get("sentiment_score") or 0))
        for p in item.get("positive_points") or []:
            if p not in pos:pos.append(p)
        for p in item.get("negative_points") or []:
            if p not in neg:neg.append(p)
    avg=sum(scores)/len(scores) if scores else 0.0
    overall="positive" if avg>=.15 else "negative" if avg<=-.15 else "neutral"
    return {"overall":overall,"average_score":round(avg,3),"total":len(items or []),"positive_points":pos[:4],"negative_points":neg[:4],**counts}


async def _enrich_broker_reports(reports):
    if not reports:return []
    headers={"User-Agent":"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/150.0 Safari/537.36","Referer":"https://finance.naver.com/research/"}
    async with httpx.AsyncClient(timeout=10,follow_redirects=True,headers=headers) as client:
        results=await asyncio.gather(*[_enrich_broker_report_item(client,item) for item in reports],return_exceptions=True)
    out=[]
    for original,result in zip(reports,results):
        if isinstance(result,Exception):
            fallback={**original,"analysis_basis":"리포트 제목"};fallback.update(_report_analysis(original.get("title") or "",""));out.append(fallback)
        else:out.append(result)
    return out

async def _fetch_broker_reports_live(stock: Stock, limit: int = 5):
    """
    Naver Finance 종목분석 리포트의 최근 리포트 링크만 조회합니다.
    리포트 본문/PDF를 StockLog DB에 복제하지 않습니다.

    1) itemCode 검색 파라미터를 우선 사용
    2) 결과가 없으면 최신 게시판 여러 페이지에서 종목명으로 fallback
    """
    limit = max(1, min(int(limit), 10))

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 "
            "Chrome/150.0 Safari/537.36"
        ),
        "Referer": "https://finance.naver.com/research/",
    }

    async with httpx.AsyncClient(
        timeout=15,
        follow_redirects=True,
        headers=headers,
    ) as client:
        candidates = [
            {
                "searchType": "itemCode",
                "itemCode": stock.code,
            },
            {
                "searchType": "itemName",
                "itemName": stock.name,
            },
        ]

        last_error = None

        for params in candidates:
            try:
                r = await client.get(
                    NAVER_RESEARCH_URL,
                    params=params,
                )
                r.raise_for_status()
                reports = _parse_naver_reports(
                    r.text,
                    stock,
                    limit,
                )
                if reports:
                    enriched=await _enrich_broker_reports(reports)
                    return {"items":enriched,"summary":_report_summary(enriched),"source":"naver-finance-research","warning":None}
            except Exception as exc:
                last_error = exc

        # 검색 파라미터 결과가 없을 경우 최근 페이지를 짧게 scan
        collected = []
        seen = set()

        for page in range(1, 9):
            try:
                r = await client.get(
                    NAVER_RESEARCH_URL,
                    params={"page": page},
                )
                r.raise_for_status()
                rows = _parse_naver_reports(
                    r.text,
                    stock,
                    limit,
                )

                for item in rows:
                    key = (
                        item["title"],
                        item["broker"],
                        item["date"],
                    )
                    if key not in seen:
                        seen.add(key)
                        collected.append(item)

                    if len(collected) >= limit:
                        enriched=await _enrich_broker_reports(collected[:limit])
                        return {"items":enriched,"summary":_report_summary(enriched),"source":"naver-finance-research","warning":None}
            except Exception as exc:
                last_error = exc
                break

    final_items=collected[:limit] if "collected" in locals() else []
    enriched=await _enrich_broker_reports(final_items)
    return {"items":enriched,"summary":_report_summary(enriched),"source":"naver-finance-research","warning":(f"증권사 리포트 조회 실패: {last_error}" if last_error else "최근 종목분석 리포트가 없습니다.")}


def _parse_report_date(text):
    raw=str(text or "").strip()
    for fmt in ("%y.%m.%d","%Y.%m.%d","%Y-%m-%d","%Y%m%d"):
        try:return datetime.strptime(raw,fmt)
        except Exception:pass
    return None


def _broker_cache_json(row):
    return {
        "company":"",
        "title":row.title,
        "broker":row.broker or "",
        "date":row.report_date or "",
        "report_dt":row.report_dt.isoformat() if row.report_dt else None,
        "link":row.link,
        "source":"Naver Finance Research cache",
        "sentiment":row.sentiment or "neutral",
        "sentiment_score":float(row.sentiment_score or 0),
        "brief_summary":row.brief_summary or "",
        "investment_opinion":row.investment_opinion or "",
        "target_price":row.target_price,
        "analysis_basis":row.analysis_basis or "리포트 제목",
        "positive_points":[],"negative_points":[],
    }


async def get_broker_reports(stock:Stock,limit:int=5,db:Session|None=None,force:bool=False):
    """Broker reports with DB cache. Live crawling is not repeated on every detail open."""
    limit=max(1,min(int(limit),20))
    ttl=int(os.getenv("BROKER_REPORT_CACHE_SECONDS","21600"))
    cached=[]; latest=None
    if db is not None:
        report_cutoff=datetime.now()-timedelta(days=183)
        cached=(db.query(BrokerReportCache).filter(BrokerReportCache.stock_code==stock.code,BrokerReportCache.report_dt>=report_cutoff).order_by(BrokerReportCache.report_dt.desc(),BrokerReportCache.id.desc()).limit(max(limit,20)).all())
        latest=max((x.fetched_at for x in cached if x.fetched_at),default=None)
        if cached and not force and latest and datetime.now()-latest<timedelta(seconds=ttl):
            items=[_broker_cache_json(x) for x in cached[:limit]]
            return {"items":items,"summary":_report_summary(items),"source":"mysql-broker-report-cache","warning":None,"fetched":False,"last_fetched_at":latest.isoformat()}
    if db is not None:
        # Cached report reads are complete; do not hold their transaction during crawl.
        commit_or_rollback(db)
    result=await _fetch_broker_reports_live(stock,limit=max(limit,10))
    items=result.get("items") or []
    # Keep collection and display scope aligned: reports without a trustworthy date,
    # or older than roughly six months, are not persisted into the active feed.
    live_cutoff=datetime.now()-timedelta(days=183)
    items=[x for x in items if (_parse_report_date(x.get("date")) is not None and _parse_report_date(x.get("date"))>=live_cutoff)]
    # Actual report date is authoritative for ordering; never use fetch time as report time.
    items=sorted(items,key=lambda x:(_parse_report_date(x.get("date")) or datetime.min),reverse=True)
    if db is not None and items:
        now=datetime.now()
        links=[x.get("link") for x in items if x.get("link")]
        existing={x.link:x for x in db.query(BrokerReportCache).filter(BrokerReportCache.stock_code==stock.code,BrokerReportCache.link.in_(links)).all()} if links else {}
        for item in items:
            link=item.get("link") or ""
            if not link:continue
            row=existing.get(link)
            if row is None:
                row=BrokerReportCache(stock_code=stock.code,link=link);db.add(row)
            row.title=item.get("title") or "";row.broker=item.get("broker") or "";row.report_date=item.get("date") or "";row.report_dt=_parse_report_date(item.get("date"))
            row.investment_opinion=item.get("investment_opinion") or "";row.target_price=item.get("target_price");row.sentiment=item.get("sentiment") or "neutral";row.sentiment_score=float(item.get("sentiment_score") or 0)
            row.brief_summary=item.get("brief_summary") or "";row.analysis_basis=item.get("analysis_basis") or "";row.fetched_at=now
        commit_or_rollback(db)
        cached=(db.query(BrokerReportCache).filter(BrokerReportCache.stock_code==stock.code,BrokerReportCache.report_dt>=report_cutoff).order_by(BrokerReportCache.report_dt.desc(),BrokerReportCache.id.desc()).limit(limit).all())
        items=[_broker_cache_json(x) for x in cached]
        result={**result,"items":items,"summary":_report_summary(items),"source":"naver-finance-research+mysql","fetched":True,"last_fetched_at":now.isoformat()}
    return result


_DISCLOSURE_IMPORTANCE={
    "잠정실적":95,"영업실적":92,"단일판매":94,"공급계약":94,"유상증자":98,"무상증자":86,
    "합병":98,"분할":96,"최대주주":92,"자기주식":88,"자사주":88,"배당":84,
    "소송":94,"횡령":100,"배임":100,"거래정지":100,"상장폐지":100,"회생":100,
    "투자판단":90,"타법인":84,"신규시설":82,"사업보고서":78,"반기보고서":76,"분기보고서":74,
}


def _disclosure_importance(report_name):
    name=str(report_name or "")
    best=60.0;matched=[]
    for key,score in _DISCLOSURE_IMPORTANCE.items():
        if key in name:
            best=max(best,float(score));matched.append(key)
    return best,("중요 공시: "+", ".join(matched[:3])) if matched else "일반 공시"


def _disclosure_json(row):
    return {"receipt_no":row.receipt_no,"report_name":row.report_name,"filer_name":row.filer_name or "","receipt_date":row.receipt_date or "","receipt_dt":row.receipt_dt.isoformat() if row.receipt_dt else None,"remark":row.remark or "","link":row.link or "","importance_score":float(row.importance_score or 0),"importance_reason":row.importance_reason or ""}


async def get_stock_disclosures(stock:Stock,db:Session,force:bool=False,days:int=180,limit:int=20):
    """Recent official OpenDART disclosures, cached and ranked by filing date/importance."""
    key=(get_provider_credentials(PROVIDER_DART,db).get("api_key") or "").strip();limit=max(1,min(int(limit),50));days=max(7,min(int(days),365))
    cached=(db.query(DisclosureCache).filter(DisclosureCache.stock_code==stock.code).order_by(DisclosureCache.receipt_dt.desc(),DisclosureCache.id.desc()).limit(limit).all())
    latest=max((x.fetched_at for x in cached if x.fetched_at),default=None)
    ttl=int(os.getenv("DISCLOSURE_CACHE_SECONDS","21600"))
    if not force and cached and latest and datetime.now()-latest<timedelta(seconds=ttl):
        items=[_disclosure_json(x) for x in cached]
        return {"items":items,"important_items":sorted(items,key=lambda x:x["importance_score"],reverse=True)[:5],"source":"mysql-opendart-disclosure-cache","fetched":False,"last_fetched_at":latest.isoformat(),"warning":None}
    if not key:
        items=[_disclosure_json(x) for x in cached]
        return {"items":items,"important_items":sorted(items,key=lambda x:x["importance_score"],reverse=True)[:5],"source":"mysql-opendart-disclosure-cache" if items else "unavailable","fetched":False,"warning":"OpenDART API 키가 없어 최신 공시를 조회하지 못했습니다."}
    if not stock.corp_code:
        return {"items":[],"important_items":[],"source":"unavailable","fetched":False,"warning":"OpenDART corp_code가 없어 공시를 조회하지 못했습니다."}
    end=datetime.now().date();begin=end-timedelta(days=days)
    params={"crtfc_key":key,"corp_code":stock.corp_code,"bgn_de":begin.strftime("%Y%m%d"),"end_de":end.strftime("%Y%m%d"),"page_no":1,"page_count":100,"last_reprt_at":"N"}
    # Credential/cache reads are complete. Release the request transaction before OpenDART.
    commit_or_rollback(db)
    try:
        async with httpx.AsyncClient(timeout=15,follow_redirects=True) as client:
            r=await tracked_get(client,PROVIDER_DART,"list","https://opendart.fss.or.kr/api/list.json",request_kind="manual" if force else "interactive",stock_code=stock.code,params=params);r.raise_for_status();payload=r.json()
        status=str(payload.get("status") or "")
        if status not in ("000","013"):
            raise RuntimeError(payload.get("message") or f"OpenDART status={status}")
        rows=payload.get("list") or [];now=datetime.now();receipt_nos=[str(x.get("rcept_no") or "") for x in rows if x.get("rcept_no")]
        existing={x.receipt_no:x for x in db.query(DisclosureCache).filter(DisclosureCache.receipt_no.in_(receipt_nos)).all()} if receipt_nos else {}
        for item in rows:
            no=str(item.get("rcept_no") or "");name=str(item.get("report_nm") or "");date=str(item.get("rcept_dt") or "")
            if not no or not name:continue
            row=existing.get(no)
            if row is None:
                row=DisclosureCache(stock_code=stock.code,corp_code=stock.corp_code or "",receipt_no=no);db.add(row)
            score,reason=_disclosure_importance(name)
            row.report_name=name;row.filer_name=str(item.get("flr_nm") or "");row.receipt_date=date;row.receipt_dt=_parse_pubdate(date);row.remark=str(item.get("rm") or "")
            row.link=f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={no}";row.importance_score=score;row.importance_reason=reason;row.fetched_at=now
        commit_or_rollback(db)
    except Exception as exc:
        items=[_disclosure_json(x) for x in cached]
        msg=str(exc or "")
        quota=any(token in msg.lower() for token in ("사용한도", "limit", "quota", "020", "429"))
        warning=(
            "OpenDART 일일 호출 한도에 도달해 저장된 최근 공시를 표시합니다. StockLog는 6시간 캐시를 사용해 불필요한 재호출을 줄입니다."
            if quota else f"OpenDART 공시 조회 실패: {exc}"
        )
        return {"items":items,"important_items":sorted(items,key=lambda x:x["importance_score"],reverse=True)[:5],"source":"mysql-opendart-disclosure-cache" if items else "opendart-error","fetched":False,"warning":warning,"quota_limited":quota}
    cached=(db.query(DisclosureCache).filter(DisclosureCache.stock_code==stock.code).order_by(DisclosureCache.receipt_dt.desc(),DisclosureCache.id.desc()).limit(limit).all())
    items=[_disclosure_json(x) for x in cached]
    return {"items":items,"important_items":sorted(items,key=lambda x:(x["importance_score"],x.get("receipt_dt") or ""),reverse=True)[:5],"source":"opendart+mysql","fetched":True,"last_fetched_at":datetime.now().isoformat(),"warning":None}



# ---------------------------------------------------------
# OpenDART company overview -> representative business class
# ---------------------------------------------------------

# These are broad BUSINESS labels derived from OpenDART's official
# `induty_code`; they are not generated market themes.
DART_INDUSTRY_DIVISIONS = {
    "01": "농업", "02": "임업", "03": "수산업",
    "05": "석탄광업", "06": "원유·가스", "07": "금속광업", "08": "비금속광업",
    "10": "식품", "11": "음료", "12": "담배", "13": "섬유", "14": "의류",
    "15": "가죽·신발", "16": "목재", "17": "제지", "18": "인쇄",
    "19": "정유·석유제품", "20": "화학", "21": "제약", "22": "고무·플라스틱",
    "23": "건자재·비금속", "24": "철강·금속", "25": "금속가공",
    "26": "전자부품·컴퓨터", "27": "의료·정밀기기", "28": "전기장비",
    "29": "기계·장비", "30": "자동차·부품", "31": "조선·운송장비",
    "32": "가구", "33": "기타 제조", "34": "산업장비 수리",
    "35": "전력·가스", "36": "수도", "37": "환경·하수처리",
    "38": "폐기물·재활용", "39": "환경복원",
    "41": "건축", "42": "건설·인프라",
    "45": "자동차 유통·정비", "46": "도매", "47": "소매·유통",
    "49": "육상운송", "50": "해운", "51": "항공", "52": "물류·창고",
    "55": "숙박", "56": "외식",
    "58": "소프트웨어·콘텐츠", "59": "영상·엔터테인먼트",
    "60": "방송", "61": "통신", "62": "IT서비스·시스템개발", "63": "정보서비스",
    "64": "금융", "65": "보험", "66": "금융지원", "68": "부동산",
    "70": "연구개발", "71": "전문서비스", "72": "엔지니어링",
    "73": "광고", "74": "기타 전문서비스", "75": "사업지원", "76": "렌탈",
    "84": "공공행정", "85": "교육", "86": "의료서비스", "87": "사회복지",
    "90": "예술·콘텐츠", "91": "스포츠·레저",
    "95": "수리서비스", "96": "개인서비스",
}


def dart_industry_name(industry_code: str):
    digits=re.sub(
        r"[^0-9]",
        "",
        str(industry_code or ""),
    )
    if len(digits) < 2:
        return ""
    return DART_INDUSTRY_DIVISIONS.get(
        digits[:2],
        "기타 사업",
    )


async def fetch_dart_company_profile(
    stock: Stock,
    *,
    client=None,
    db: Session | None = None,
):
    """
    Fetch actual OpenDART 기업개황 (`/api/company.json`).

    Uses official `induty_code` as the fallback business classification.
    """
    key=(get_provider_credentials(PROVIDER_DART,db).get("api_key") or "").strip()

    if not key or not stock.corp_code:
        return None

    own_client=(client is None)
    http_client=(
        httpx.AsyncClient(timeout=15)
        if own_client
        else client
    )

    try:
        response=await tracked_get(
            http_client, PROVIDER_DART, "company",
            "https://opendart.fss.or.kr/api/company.json", request_kind="background", stock_code=stock.code,
            params={
                "crtfc_key":key,
                "corp_code":stock.corp_code,
            },
        )
        response.raise_for_status()
        data=response.json()

        dart_status=str(data.get("status") or "")
        if dart_status == "013":
            return None
        if dart_status != "000":
            message=str(data.get("message") or "OpenDART 기업개황 오류").strip()
            raise RuntimeError(f"OpenDART company status={dart_status or 'unknown'}: {message}")

        code=str(data.get("induty_code") or "").strip()
        if not code:
            return None

        name=dart_industry_name(code)
        if not name:
            return None

        return {
            "industry_code":code,
            "industry_name":name,
            "source":"opendart",
            "corp_name":str(data.get("corp_name") or "").strip(),
        }
    finally:
        if own_client:
            await http_client.aclose()


async def sync_dart_corp_codes(db:Session):
    key=(get_provider_credentials(PROVIDER_DART,db).get('api_key') or '').strip()
    if not key: return {"configured":False,"mapped":0,"message":"OpenDART API 키가 설정되지 않았습니다."}
    # Credential SELECT is complete. A corpCode download may take up to 60s;
    # release this caller session's connection before network I/O.
    commit_or_rollback(db)
    async with httpx.AsyncClient(timeout=60) as c:
        r=await tracked_get(c,PROVIDER_DART,'corpCode','https://opendart.fss.or.kr/api/corpCode.xml',request_kind='manual',params={'crtfc_key':key}); r.raise_for_status(); raw=r.content
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            name=next(n for n in z.namelist() if n.lower().endswith('.xml')); xml=z.read(name)
    except Exception as e: raise RuntimeError(f'OpenDART corpCode.xml ZIP 파싱 실패: {e}')
    root=ET.fromstring(xml); mapping={}
    for n in root.findall('.//list'):
        sc=(n.findtext('stock_code') or '').strip(); cc=(n.findtext('corp_code') or '').strip()
        if sc and cc: mapping[sc]=cc
    mapped=0
    # StockLog only enriches the canonical KOSPI/KOSDAQ company universe.
    # Excluded raw securities remain in DB solely for historical/FK safety.
    for s in db.query(Stock).filter(Stock.is_active==True,Stock.is_analysis_eligible==True,Stock.market.in_(["KOSPI","KOSDAQ"])).all():
        cc=mapping.get(s.code)
        if cc and s.corp_code!=cc: s.corp_code=cc; mapped+=1
    commit_or_rollback(db); return {"configured":True,"mapped":mapped,"available":len(mapping)}

def _financial_number(item, *fields):
    if not item:
        return None
    for key in fields:
        value=item.get(key)
        if value in (None,"","-","--"):
            continue
        try:
            return float(str(value).replace(",","").strip())
        except Exception:
            continue
    return None


def _financial_account_map(items):
    """Prefer consolidated statements and retain comparison columns per account."""
    for fs in ("CFS","OFS"):
        selected=[item for item in items if item.get("fs_div")==fs]
        if selected:
            break
    else:
        selected=list(items or [])
    mapped={}
    for item in selected:
        name=(item.get("account_nm") or "").strip()
        if name and name not in mapped:
            mapped[name]=item
    return mapped


def _account_item(mapped, *names):
    for name in names:
        if mapped.get(name):
            return mapped[name]
    return None


def _current_income(item, label):
    # Quarterly/half-year reports are shown on a cumulative YTD basis so that
    # the official previous-period cumulative amount is directly comparable.
    if label in {"1Q","2Q","3Q"}:
        return _financial_number(item,"thstrm_add_amount","thstrm_amount")
    return _financial_number(item,"thstrm_amount","thstrm_add_amount")


def _previous_income(item, label):
    if label in {"1Q","2Q","3Q"}:
        # Do not fall back to frmtrm_amount here.  For interim filings that
        # field can represent a different basis; the cumulative comparison is
        # the like-for-like value documented by the filing API.
        return _financial_number(item,"frmtrm_add_amount")
    return _financial_number(item,"frmtrm_amount")


def _current_balance(item):
    return _financial_number(item,"thstrm_amount")


def _previous_balance(item):
    return _financial_number(item,"frmtrm_amount")


async def fetch_dart_financials(stock:Stock,db:Session):
    key=(get_provider_credentials(PROVIDER_DART,db).get('api_key') or '').strip()
    if not key or not stock.corp_code:return []
    now=datetime.now(); cand=[]
    for y in (now.year,now.year-1,now.year-2):
        cand += [(y,'11014','3Q'),(y,'11012','2Q'),(y,'11013','1Q'),(y,'11011','FY')]
    rows=[]
    async with httpx.AsyncClient(timeout=20) as c:
        for y,rc,label in cand:
            try:
                r=await tracked_get(c,PROVIDER_DART,'financials','https://opendart.fss.or.kr/api/fnlttSinglAcnt.json',request_kind='background',stock_code=stock.code,params={'crtfc_key':key,'corp_code':stock.corp_code,'bsns_year':str(y),'reprt_code':rc})
                r.raise_for_status(); d=r.json()
                if d.get('status')!='000':continue
                mapped=_financial_account_map(d.get('list',[]))
                if not mapped:continue

                revenue_item=_account_item(mapped,'매출액','영업수익','수익(매출액)')
                op_item=_account_item(mapped,'영업이익','영업이익(손실)')
                net_item=_account_item(mapped,'당기순이익','당기순이익(손실)','분기순이익','반기순이익')
                assets_item=_account_item(mapped,'자산총계')
                liabilities_item=_account_item(mapped,'부채총계')
                equity_item=_account_item(mapped,'자본총계')

                income_period=(f'{y-1}-{label} 누적' if label in {'1Q','2Q','3Q'} else f'{y-1}-FY' if label=='FY' else None)
                balance_period=f'{y-1}-FY' if label in {'1Q','2Q','3Q','FY'} else None
                rows.append({
                    'period':f'{y}-{label}',
                    'revenue':_current_income(revenue_item,label),
                    'operating_profit':_current_income(op_item,label),
                    'net_income':_current_income(net_item,label),
                    'assets':_current_balance(assets_item),
                    'liabilities':_current_balance(liabilities_item),
                    'equity':_current_balance(equity_item),
                    'comparison_revenue':_previous_income(revenue_item,label),
                    'comparison_operating_profit':_previous_income(op_item,label),
                    'comparison_net_income':_previous_income(net_item,label),
                    'comparison_assets':_previous_balance(assets_item),
                    'comparison_liabilities':_previous_balance(liabilities_item),
                    'comparison_equity':_previous_balance(equity_item),
                    'comparison_income_period':income_period,
                    'comparison_balance_period':balance_period,
                    'income_basis':'누적' if label in {'1Q','2Q','3Q'} else '연간',
                })
                if len(rows)>=4:break
            except Exception:continue
    return rows


REPORT_CODE_BY_LABEL = {
    "1Q": "11013",
    "2Q": "11012",
    "3Q": "11014",
    "FY": "11011",
}


def _safe_number(value):
    if value in (None, "", "-", "--"):
        return None
    try:
        return float(
            str(value)
            .replace(",", "")
            .strip()
        )
    except Exception:
        return None


def _period_parts(period):
    try:
        year_text, label = str(period).split("-", 1)
        return int(year_text), label
    except Exception:
        return 0, ""


def _period_rank(period):
    year, label = _period_parts(period)
    order = {
        "1Q": 1,
        "2Q": 2,
        "3Q": 3,
        "FY": 4,
    }
    return year, order.get(label, 0)


def _latest_financial_row(rows):
    if not rows:
        return None
    return max(
        rows,
        key=lambda x: _period_rank(
            x.get("period", "")
        ),
    )


def _latest_fy_row(rows):
    fy = [
        x
        for x in rows
        if str(
            x.get("period", "")
        ).endswith("-FY")
    ]
    return (
        max(
            fy,
            key=lambda x: _period_rank(
                x.get("period", "")
            ),
        )
        if fy
        else None
    )


def _annualized_net_income(row):
    if not row:
        return None

    net_income = _safe_number(
        row.get("net_income")
    )
    if net_income is None:
        return None

    _, label = _period_parts(
        row.get("period", "")
    )

    factor = {
        "1Q": 4.0,
        "2Q": 2.0,
        "3Q": 4.0 / 3.0,
        "FY": 1.0,
    }.get(label, 1.0)

    return net_income * factor


async def fetch_dart_share_count(
    stock: Stock,
    financial_rows,
    db: Session | None = None,
):
    """
    OpenDART 주식의 총수 현황:
    /api/stockTotqySttus.json

    보통주를 우선 사용하며,
    유통주식수 -> 발행주식수 순서로 fallback 합니다.
    """
    key = (get_provider_credentials(PROVIDER_DART,db).get("api_key") or "").strip()

    if not key or not stock.corp_code:
        return None

    candidate_periods = []

    latest = _latest_financial_row(
        financial_rows
    )
    latest_fy = _latest_fy_row(
        financial_rows
    )

    for row in (
        latest,
        latest_fy,
    ):
        if (
            row
            and row.get("period")
            not in candidate_periods
        ):
            candidate_periods.append(
                row.get("period")
            )

    for row in sorted(
        financial_rows,
        key=lambda x: _period_rank(
            x.get("period", "")
        ),
        reverse=True,
    ):
        period = row.get("period")
        if period not in candidate_periods:
            candidate_periods.append(
                period
            )

    async with httpx.AsyncClient(
        timeout=20
    ) as client:
        for period in candidate_periods:
            year, label = _period_parts(
                period
            )
            report_code = (
                REPORT_CODE_BY_LABEL.get(
                    label
                )
            )

            if not year or not report_code:
                continue

            try:
                response = await tracked_get(
                    client, PROVIDER_DART, "share-count",
                    "https://opendart.fss.or.kr/api/stockTotqySttus.json", request_kind="background", stock_code=stock.code,
                    params={
                        "crtfc_key": key,
                        "corp_code": stock.corp_code,
                        "bsns_year": str(year),
                        "reprt_code": report_code,
                    },
                )
                response.raise_for_status()
                data = response.json()

                if data.get("status") != "000":
                    continue

                items = data.get(
                    "list",
                    [],
                )

                if not items:
                    continue

                common_rows = [
                    x for x in items
                    if "보통" in str(
                        x.get("se", "")
                    )
                ]

                total_rows = [
                    x for x in items
                    if "합계" in str(
                        x.get("se", "")
                    )
                ]

                candidates = (
                    common_rows
                    or total_rows
                    or items
                )

                for item in candidates:
                    distributed = _safe_number(
                        item.get(
                            "distb_stock_co"
                        )
                    )
                    issued = _safe_number(
                        item.get(
                            "istc_totqy"
                        )
                    )

                    shares = (
                        distributed
                        if distributed
                        and distributed > 0
                        else issued
                    )

                    if shares and shares > 0:
                        return {
                            "shares": shares,
                            "period": period,
                            "security_type": str(
                                item.get(
                                    "se",
                                    "",
                                )
                            ),
                            "distributed_shares": distributed,
                            "issued_shares": issued,
                        }

            except Exception:
                continue

    return None


async def fetch_dart_dividend_yield(
    stock: Stock,
    financial_rows,
    db: Session | None = None,
):
    """
    OpenDART '배당에 관한 사항' alotMatter.json.

    최근 사업보고서(FY)를 우선 조회하고,
    응답의 보통주 '현금배당수익률(%)' 당기 값을 사용합니다.
    데이터가 없으면 None을 반환하며 가짜 값은 만들지 않습니다.
    """
    key = (get_provider_credentials(PROVIDER_DART,db).get("api_key") or "").strip()

    if not key or not stock.corp_code:
        return None

    years = []

    for row in sorted(
        financial_rows or [],
        key=lambda x: _period_rank(
            x.get("period", "")
        ),
        reverse=True,
    ):
        year, _ = _period_parts(
            row.get("period", "")
        )
        if year and year not in years:
            years.append(year)

    now_year = datetime.now().year
    for year in (
        now_year,
        now_year - 1,
        now_year - 2,
    ):
        if year not in years:
            years.append(year)

    async with httpx.AsyncClient(
        timeout=20
    ) as client:
        for year in years[:3]:
            try:
                response = await tracked_get(
                    client, PROVIDER_DART, "dividend",
                    "https://opendart.fss.or.kr/api/alotMatter.json", request_kind="background", stock_code=stock.code,
                    params={
                        "crtfc_key": key,
                        "corp_code": stock.corp_code,
                        "bsns_year": str(year),
                        "reprt_code": "11011",
                    },
                )
                response.raise_for_status()
                data = response.json()

                if data.get("status") != "000":
                    continue

                items = data.get("list", [])

                # API 응답은 se 컬럼에 지표명이 들어갑니다.
                candidates = [
                    item
                    for item in items
                    if "현금배당수익률" in str(
                        item.get("se", "")
                    )
                ]

                common = [
                    item
                    for item in candidates
                    if "보통" in str(
                        item.get("stock_knd", "")
                    )
                ]

                for item in (
                    common
                    or candidates
                ):
                    value = _safe_number(
                        item.get("thstrm")
                    )

                    if value is not None:
                        return {
                            "yield": value,
                            "year": year,
                            "stock_type": str(
                                item.get(
                                    "stock_knd",
                                    "",
                                )
                            ),
                        }

            except Exception:
                continue

    return None


def _financial_performance_metrics(rows):
    """
    최신 DART 재무행 기준으로:
    - 영업이익률 = 영업이익 / 매출 * 100
    - 매출성장률 = 같은 보고서 구분의 전년 동기만 비교
      (서로 다른 분기/누적기간을 임의 비교하지 않음)
    """
    if not rows:
        return {
            "revenue_growth": None,
            "operating_margin": None,
        }

    latest = _latest_financial_row(rows)
    if not latest:
        return {
            "revenue_growth": None,
            "operating_margin": None,
        }

    revenue = _safe_number(
        latest.get("revenue")
    )
    operating_profit = _safe_number(
        latest.get("operating_profit")
    )

    operating_margin = (
        operating_profit / revenue * 100
        if revenue not in (None, 0)
        and operating_profit is not None
        else None
    )

    year, label = _period_parts(
        latest.get("period", "")
    )

    comparison = None

    # Prefer the filing-native previous-year cumulative comparison captured
    # together with the current report.  This avoids mixing 2Q cumulative
    # revenue with 1Q, or 3Q cumulative revenue with a different period.
    previous_revenue = _safe_number(latest.get("comparison_revenue"))

    if previous_revenue is None:
        for row in rows:
            row_year, row_label = _period_parts(row.get("period", ""))
            if row_year == year - 1 and row_label == label:
                comparison = row
                previous_revenue = _safe_number(row.get("revenue"))
                break

    revenue_growth = (
        (revenue - previous_revenue)
        / abs(previous_revenue)
        * 100
        if revenue is not None
        and previous_revenue not in (
            None,
            0,
        )
        else None
    )

    return {
        "revenue_growth": (
            round(revenue_growth, 4)
            if revenue_growth is not None
            else None
        ),
        "operating_margin": (
            round(operating_margin, 4)
            if operating_margin is not None
            else None
        ),
    }


def calculate_dart_valuation(
    stock,
    financial_rows,
    share_info,
):
    """
    DART 실제 재무/주식수 + Kiwoom 현재가.

    EPS = 연간 순이익 / 주식수
    BPS = 최신 자기자본 / 주식수
    ROE = 연간 순이익 / 최신 자기자본
    PER = 현재가 / EPS
    PBR = 현재가 / BPS

    EPS/PER 순이익은 FY 우선.
    FY가 없을 때만 최신 기간 실적을 연환산합니다.
    """
    if not financial_rows:
        return {
            "ok": False,
            "reason": "OpenDART 재무제표가 없습니다.",
        }

    if (
        not share_info
        or not share_info.get("shares")
    ):
        return {
            "ok": False,
            "reason": (
                "OpenDART 주식의 총수 현황에서 "
                "주식수를 확보하지 못했습니다."
            ),
        }

    latest = _latest_financial_row(
        financial_rows
    )
    fy = _latest_fy_row(
        financial_rows
    )

    if not latest:
        return {
            "ok": False,
            "reason": "최신 재무기간을 찾지 못했습니다.",
        }

    shares = float(
        share_info["shares"]
    )

    equity = _safe_number(
        latest.get("equity")
    )

    income_source = fy or latest

    annual_net = (
        _safe_number(
            fy.get("net_income")
        )
        if fy
        else _annualized_net_income(
            latest
        )
    )

    eps = (
        annual_net / shares
        if annual_net is not None
        and shares > 0
        else None
    )

    bps = (
        equity / shares
        if equity is not None
        and shares > 0
        else None
    )

    roe = (
        annual_net
        / equity
        * 100
        if annual_net is not None
        and equity
        and equity > 0
        else None
    )

    performance = _financial_performance_metrics(
        financial_rows
    )

    price = float(
        stock.price or 0
    )

    per = (
        price / eps
        if price > 0
        and eps is not None
        and eps > 0
        else None
    )

    pbr = (
        price / bps
        if price > 0
        and bps is not None
        and bps > 0
        else None
    )

    return {
        "ok": True,
        "shares_outstanding": shares,
        "eps": round(eps, 4)
        if eps is not None
        else None,
        "bps": round(bps, 4)
        if bps is not None
        else None,
        "roe": round(roe, 4)
        if roe is not None
        else None,
        "per": round(per, 4)
        if per is not None
        else None,
        "pbr": round(pbr, 4)
        if pbr is not None
        else None,
        "revenue_growth": performance.get(
            "revenue_growth"
        ),
        "operating_margin": performance.get(
            "operating_margin"
        ),
        "financial_period": latest.get(
            "period"
        ),
        "income_period": (
            income_source.get("period")
            if income_source
            else None
        ),
        "share_period": share_info.get(
            "period"
        ),
        "income_basis": (
            "FY"
            if fy
            else "annualized-latest-period"
        ),
    }


def apply_dart_valuation(
    stock,
    valuation,
):
    if not valuation.get("ok"):
        return False

    stock.shares_outstanding = (
        valuation.get(
            "shares_outstanding"
        )
    )
    stock.eps = valuation.get("eps")
    stock.bps = valuation.get("bps")
    stock.roe = valuation.get("roe")
    stock.per = valuation.get("per")
    stock.pbr = valuation.get("pbr")
    stock.revenue_growth = valuation.get(
        "revenue_growth"
    )
    stock.operating_margin = valuation.get(
        "operating_margin"
    )
    stock.valuation_calculated_at = (
        datetime.now()
    )

    if (
        stock.price
        and stock.shares_outstanding
    ):
        # stock.market_cap unit: 억원
        stock.market_cap = round(
            float(stock.price)
            * float(
                stock.shares_outstanding
            )
            / 100_000_000,
            4,
        )

    return True


def recalculate_price_multiples(
    stock,
):
    """
    Kiwoom 현재가가 갱신될 때 기존 DART EPS/BPS로
    PER/PBR/시가총액을 즉시 다시 계산.
    """
    price = float(
        stock.price or 0
    )

    if (
        price > 0
        and stock.eps is not None
        and stock.eps > 0
    ):
        stock.per = round(
            price / stock.eps,
            4,
        )
    elif (
        stock.eps is not None
        and stock.eps <= 0
    ):
        stock.per = None

    if (
        price > 0
        and stock.bps is not None
        and stock.bps > 0
    ):
        stock.pbr = round(
            price / stock.bps,
            4,
        )

    if (
        price > 0
        and stock.shares_outstanding
    ):
        stock.market_cap = round(
            price
            * float(
                stock.shares_outstanding
            )
            / 100_000_000,
            4,
        )


def upsert_financials(stock_code,rows,db:Session):
    if not rows:return {'inserted':0,'updated':0}
    periods=[str(x['period']) for x in rows]
    ex={x.period:x for x in db.query(FinancialQuarter).filter(FinancialQuarter.stock_code==stock_code,FinancialQuarter.period.in_(periods)).all()}
    ins=upd=0
    for i in rows:
        period=str(i['period']); row=ex.get(period)
        if not row:row=FinancialQuarter(stock_code=stock_code,period=period);db.add(row);ins+=1
        else:upd+=1
        row.revenue=_safe_number(i.get('revenue'));row.operating_profit=_safe_number(i.get('operating_profit'));row.net_income=_safe_number(i.get('net_income'));row.assets=_safe_number(i.get('assets'));row.liabilities=_safe_number(i.get('liabilities'));row.equity=_safe_number(i.get('equity'))
        row.comparison_revenue=_safe_number(i.get('comparison_revenue'));row.comparison_operating_profit=_safe_number(i.get('comparison_operating_profit'));row.comparison_net_income=_safe_number(i.get('comparison_net_income'))
        row.comparison_assets=_safe_number(i.get('comparison_assets'));row.comparison_liabilities=_safe_number(i.get('comparison_liabilities'));row.comparison_equity=_safe_number(i.get('comparison_equity'))
        row.comparison_income_period=i.get('comparison_income_period');row.comparison_balance_period=i.get('comparison_balance_period');row.income_basis=i.get('income_basis')
    try:
        commit_or_rollback(db)
    except Exception:
        # A failed flush/commit leaves SQLAlchemy in PendingRollbackError
        # state.  Always restore the Session before propagating the original
        # error so the caller can record the failed symbol and continue.
        db.rollback()
        raise
    return {'inserted':ins,'updated':upd}

def financials_from_db(stock_code,db:Session,limit=4):
    rows=db.query(FinancialQuarter).filter(FinancialQuarter.stock_code==stock_code).order_by(FinancialQuarter.period.desc()).limit(limit).all()
    return [{
        'period':x.period,'revenue':x.revenue,'operating_profit':x.operating_profit,'net_income':x.net_income,'assets':x.assets,'liabilities':x.liabilities,'equity':x.equity,
        'comparison_revenue':x.comparison_revenue,'comparison_operating_profit':x.comparison_operating_profit,'comparison_net_income':x.comparison_net_income,
        'comparison_assets':x.comparison_assets,'comparison_liabilities':x.comparison_liabilities,'comparison_equity':x.comparison_equity,
        'comparison_income_period':x.comparison_income_period,'comparison_balance_period':x.comparison_balance_period,'income_basis':x.income_basis,
    } for x in rows]
