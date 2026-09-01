from __future__ import annotations

import asyncio
import csv
import io
import json
import math
import re
import time
from datetime import date, datetime, timedelta
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import case, func, inspect, or_, text
from sqlalchemy.orm import Session

from .database import SessionLocal, engine, get_db
from .db_utils import commit_or_rollback
from .deps import current_user
from .external_api import (
    PROVIDER_ALPHA_VANTAGE,
    PROVIDER_FINNHUB,
    PROVIDER_SEC_EDGAR,
    get_provider_credentials,
    provider_public_status,
    tracked_get,
    usage_stats,
)
from .models import InvestmentProfile, OverseasPaperAccount, OverseasPaperOrder, OverseasPaperPosition, OverseasStock, User
from .smart_scoring import build_scorecard, profile_score_from_components


router = APIRouter(prefix="/api/overseas", tags=["overseas"])

US_STOCKS = [
    {"symbol":"AAPL","name":"Apple","sector":"Technology","exchange":"NASDAQ"},
    {"symbol":"MSFT","name":"Microsoft","sector":"Technology","exchange":"NASDAQ"},
    {"symbol":"NVDA","name":"NVIDIA","sector":"Semiconductors","exchange":"NASDAQ"},
    {"symbol":"GOOGL","name":"Alphabet","sector":"Communication Services","exchange":"NASDAQ"},
    {"symbol":"AMZN","name":"Amazon","sector":"Consumer Discretionary","exchange":"NASDAQ"},
    {"symbol":"META","name":"Meta Platforms","sector":"Communication Services","exchange":"NASDAQ"},
    {"symbol":"TSLA","name":"Tesla","sector":"Consumer Discretionary","exchange":"NASDAQ"},
    {"symbol":"AVGO","name":"Broadcom","sector":"Semiconductors","exchange":"NASDAQ"},
    {"symbol":"JPM","name":"JPMorgan Chase","sector":"Financials","exchange":"NYSE"},
    {"symbol":"V","name":"Visa","sector":"Financials","exchange":"NYSE"},
    {"symbol":"LLY","name":"Eli Lilly","sector":"Health Care","exchange":"NYSE"},
    {"symbol":"UNH","name":"UnitedHealth","sector":"Health Care","exchange":"NYSE"},
    {"symbol":"XOM","name":"Exxon Mobil","sector":"Energy","exchange":"NYSE"},
    {"symbol":"COST","name":"Costco","sector":"Consumer Staples","exchange":"NASDAQ"},
    {"symbol":"WMT","name":"Walmart","sector":"Consumer Staples","exchange":"NYSE"},
    {"symbol":"NFLX","name":"Netflix","sector":"Communication Services","exchange":"NASDAQ"},
    {"symbol":"AMD","name":"AMD","sector":"Semiconductors","exchange":"NASDAQ"},
    {"symbol":"CRM","name":"Salesforce","sector":"Technology","exchange":"NYSE"},
    {"symbol":"KO","name":"Coca-Cola","sector":"Consumer Staples","exchange":"NYSE"},
    {"symbol":"CAT","name":"Caterpillar","sector":"Industrials","exchange":"NYSE"},
]
US_STOCK_MAP = {row["symbol"]: row for row in US_STOCKS}
_CACHE: dict[str, tuple[float, Any]] = {}
_UNIVERSE_LOCK = asyncio.Lock()
NASDAQ_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
NASDAQ_OTHER_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"
NASDAQ_OTHER_EXCHANGES = {
    "A": ("NYSE American", "XASE"),
    "N": ("NYSE", "XNYS"),
    "P": ("NYSE Arca", "ARCX"),
    "Z": ("Cboe", "BATS"),
    "V": ("IEX", "IEXG"),
}
_PRIORITY = {row["symbol"]: index for index, row in enumerate(US_STOCKS)}
US_NAME_KO = {
    "AAPL":"애플","MSFT":"마이크로소프트","NVDA":"엔비디아","GOOGL":"알파벳","GOOG":"알파벳",
    "AMZN":"아마존","META":"메타","TSLA":"테슬라","AVGO":"브로드컴","JPM":"JP모건 체이스",
    "V":"비자","MA":"마스터카드","LLY":"일라이 릴리","UNH":"유나이티드헬스","XOM":"엑슨모빌",
    "COST":"코스트코","WMT":"월마트","NFLX":"넷플릭스","AMD":"AMD","CRM":"세일즈포스",
    "KO":"코카콜라","CAT":"캐터필러","F":"포드","GM":"제너럴 모터스","DIS":"디즈니",
    "NKE":"나이키","BA":"보잉","INTC":"인텔","QCOM":"퀄컴","ORCL":"오라클","IBM":"IBM",
    "UBER":"우버","ABNB":"에어비앤비","PLTR":"팔란티어","COIN":"코인베이스","PYPL":"페이팔",
    "SHOP":"쇼피파이","SQ":"블록","RIVN":"리비안","LCID":"루시드","MU":"마이크론",
    "TSM":"TSMC","ASML":"ASML","ARM":"ARM","SMCI":"슈퍼마이크로컴퓨터","BABA":"알리바바",
    "PDD":"핀둬둬","NIO":"니오","MCD":"맥도날드","SBUX":"스타벅스","PEP":"펩시코",
    "PG":"P&G","JNJ":"존슨앤드존슨","PFE":"화이자","MRK":"머크","ABBV":"애브비",
    "T":"AT&T","VZ":"버라이즌","TMUS":"T모바일","HD":"홈디포","LOW":"로우스",
    "GS":"골드만삭스","MS":"모건스탠리","BAC":"뱅크오브아메리카","C":"씨티그룹","WFC":"웰스파고",
    "BRK.A":"버크셔 해서웨이","BRK.B":"버크셔 해서웨이","SPY":"S&P500 ETF","QQQ":"나스닥100 ETF",
}


def ensure_overseas_schema() -> None:
    """Add overseas analysis columns for databases created by earlier releases."""
    OverseasStock.__table__.create(bind=engine,checkfirst=True)
    existing={column["name"] for column in inspect(engine).get_columns("overseas_stocks")}
    required=[("name_ko","VARCHAR(160) DEFAULT ''"),("analysis_components_json","TEXT")]
    with engine.begin() as connection:
        for column_name,ddl in required:
            if column_name not in existing:
                connection.execute(text(f"ALTER TABLE overseas_stocks ADD COLUMN {column_name} {ddl}"))


def _clean_symbol(value: str) -> str:
    symbol=str(value or "").strip().upper()
    if not re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,14}",symbol):
        raise HTTPException(422,"올바른 해외주식 티커를 입력해주세요.")
    return symbol


def _cache_get(key: str):
    row=_CACHE.get(key)
    if row and row[0]>time.monotonic():
        return row[1]
    _CACHE.pop(key,None)
    return None


def _cache_put(key: str,value: Any,ttl: int=300):
    _CACHE[key]=(time.monotonic()+ttl,value)
    return value


def _asset_type(name: str, is_etf: bool = False) -> str:
    if is_etf:
        return "etf"
    text=str(name or "").upper()
    if any(token in text for token in (" WARRANT", " RIGHT", " UNIT", " PREFERRED", " NOTE", " BOND", " DEBENTURE")):
        return "other"
    return "stock"


def _parse_nasdaq_directory(text: str, source: str) -> list[dict]:
    """Parse the official Nasdaq Trader pipe-delimited symbol directories."""
    rows=[]
    reader=csv.DictReader(io.StringIO(str(text or "")),delimiter="|")
    for raw in reader:
        if not raw or str(next(iter(raw.values()),"")).startswith("File Creation Time"):
            continue
        if str(raw.get("Test Issue") or "N").strip().upper()=="Y":
            continue
        if source=="nasdaq":
            symbol=str(raw.get("Symbol") or "").strip().upper()
            exchange,mic="NASDAQ","XNAS"
        else:
            symbol=str(raw.get("ACT Symbol") or raw.get("NASDAQ Symbol") or "").strip().upper()
            exchange,mic=NASDAQ_OTHER_EXCHANGES.get(str(raw.get("Exchange") or "").strip().upper(),("Other US",""))
        if not re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,14}",symbol):
            continue
        name=str(raw.get("Security Name") or symbol).strip().rstrip(" -")
        is_etf=str(raw.get("ETF") or "N").strip().upper()=="Y"
        rows.append({
            "symbol":symbol,"name":name or symbol,"exchange":exchange,"mic":mic,
            "currency":"USD","asset_type":_asset_type(name,is_etf),"is_etf":is_etf,
        })
    return rows


async def _download_us_universe() -> list[dict]:
    headers={"User-Agent":"StockLog US universe sync (contact via administrator settings)"}
    async with httpx.AsyncClient(timeout=25,follow_redirects=True,headers=headers) as client:
        responses=await asyncio.gather(client.get(NASDAQ_LISTED_URL),client.get(NASDAQ_OTHER_URL))
    for response in responses:
        response.raise_for_status()
    merged={}
    for row in _parse_nasdaq_directory(responses[0].text,"nasdaq")+_parse_nasdaq_directory(responses[1].text,"other"):
        merged[row["symbol"]]=row
    return sorted(merged.values(),key=lambda row:row["symbol"])


def _universe_status(db: Session) -> dict:
    total=db.query(func.count(OverseasStock.id)).filter(OverseasStock.is_active==True).scalar() or 0
    analyzed=db.query(func.count(OverseasStock.id)).filter(OverseasStock.is_active==True,OverseasStock.analysis_updated_at.isnot(None)).scalar() or 0
    quoted=db.query(func.count(OverseasStock.id)).filter(OverseasStock.is_active==True,OverseasStock.quote_updated_at.isnot(None)).scalar() or 0
    updated=db.query(func.max(OverseasStock.universe_last_seen_at)).scalar()
    return {
        "total":int(total),"analyzed":int(analyzed),"quoted":int(quoted),
        "updated_at":updated.isoformat() if updated else None,"source":"NASDAQ_TRADER",
    }


def _seed_fallback_universe(db: Session) -> None:
    if db.query(OverseasStock.id).first():
        return
    now=datetime.now()
    for index,row in enumerate(US_STOCKS):
        db.add(OverseasStock(
            symbol=row["symbol"],name=row["name"],name_ko=US_NAME_KO.get(row["symbol"],""),exchange=row["exchange"],mic="XNAS" if row["exchange"]=="NASDAQ" else "XNYS",
            asset_type="stock",source="CURATED_FALLBACK",priority=index,is_active=True,universe_last_seen_at=now,
        ))
    commit_or_rollback(db)


def _backfill_korean_names(db: Session) -> int:
    rows=db.query(OverseasStock).filter(OverseasStock.symbol.in_(list(US_NAME_KO))).all()
    changed=0
    for row in rows:
        name=US_NAME_KO.get(row.symbol,"")
        if name and row.name_ko!=name:
            row.name_ko=name;changed+=1
    if changed:
        commit_or_rollback(db)
    return changed


async def _sync_us_universe(db: Session, *, force: bool = False) -> dict:
    status=_universe_status(db)
    updated_at=None
    try:
        updated_at=datetime.fromisoformat(status["updated_at"]) if status.get("updated_at") else None
    except (TypeError,ValueError):
        updated_at=None
    if not force and status["total"]>=1000 and updated_at and datetime.now()-updated_at<timedelta(hours=12):
        return {**status,"refreshed":False}
    async with _UNIVERSE_LOCK:
        status=_universe_status(db)
        if not force and status["total"]>=1000 and status.get("updated_at"):
            try:
                if datetime.now()-datetime.fromisoformat(status["updated_at"])<timedelta(hours=12):
                    return {**status,"refreshed":False}
            except (TypeError,ValueError):
                pass
        try:
            items=await _download_us_universe()
        except Exception as exc:
            _seed_fallback_universe(db)
            return {**_universe_status(db),"refreshed":False,"warning":f"미국 종목 마스터 갱신 지연: {str(exc)[:160]}"}
        if len(items)<1000:
            _seed_fallback_universe(db)
            return {**_universe_status(db),"refreshed":False,"warning":"미국 종목 마스터 응답이 불완전해 기존 목록을 유지했습니다."}
        existing={row.symbol:row for row in db.query(OverseasStock).all()}
        now=datetime.now();seen=set()
        for item in items:
            symbol=item["symbol"];seen.add(symbol)
            row=existing.get(symbol)
            if row is None:
                row=OverseasStock(symbol=symbol);db.add(row)
            row.name=item["name"];row.name_ko=US_NAME_KO.get(symbol,row.name_ko or "");row.exchange=item["exchange"];row.mic=item["mic"]
            row.currency="USD";row.asset_type=item["asset_type"];row.is_etf=bool(item["is_etf"])
            row.is_active=True;row.source="NASDAQ_TRADER";row.priority=_PRIORITY.get(symbol,999999)
            row.universe_last_seen_at=now
        for symbol,row in existing.items():
            if symbol not in seen:
                row.is_active=False
        commit_or_rollback(db)
        return {**_universe_status(db),"refreshed":True}


def _analysis_from_quote(quote: dict) -> dict:
    fields=("price","change_percent","open","high","low","previous_close")
    available=[
        (key in quote and quote.get(key) is not None) if key=="change_percent" else float(quote.get(key) or 0)>0
        for key in fields
    ]
    coverage=round(sum(available)/len(fields)*100,1)
    if not quote.get("available") or float(quote.get("price") or 0)<=0:
        return {"score":None,"label":"분석 대기","reason":"시세 데이터가 준비되면 해외 종합점수를 계산합니다.","coverage":0.0,"components":[]}
    price=float(quote.get("price") or 0);change=float(quote.get("change_percent") or 0)
    high=float(quote.get("high") or 0);low=float(quote.get("low") or 0)
    previous=float(quote.get("previous_close") or 0);open_price=float(quote.get("open") or 0)
    volatility=((high-low)/previous*100) if previous>0 and high>=low else None
    scorecard=build_scorecard({
        "price":price,"change_rate":change,"momentum_20d":None,"volatility":volatility,
        "roe":None,"revenue_growth":None,"operating_margin":None,"per":None,"pbr":None,
        "dividend_yield":None,"market_cap":None,
    })
    direction="상승" if change>0 else "하락" if change<0 else "보합"
    position="장중 고가권" if high>low and price>=low+(high-low)*0.7 else "장중 저가권" if high>low and price<=low+(high-low)*0.3 else "장중 중간권"
    return {
        "score":scorecard["ai_score"],"label":scorecard["ai_label"],"coverage":scorecard["coverage"],
        "reason":f"전일 대비 {abs(change):.2f}% {direction}, {position}입니다. 현재 무료 시세에서 확인 가능한 주가 흐름·변동성 기준 종합점수입니다.",
        "components":scorecard["components"],
    }


def _stored_quote(row: OverseasStock | None) -> dict | None:
    if row is None or row.quote_price is None or float(row.quote_price or 0)<=0:
        return None
    age=(datetime.now()-row.quote_updated_at).total_seconds() if row.quote_updated_at else None
    return {
        "symbol":row.symbol,"price":float(row.quote_price or 0),"change":float(row.quote_change or 0),
        "change_percent":float(row.quote_change_percent or 0),"open":float(row.quote_open or 0),
        "high":float(row.quote_high or 0),"low":float(row.quote_low or 0),
        "previous_close":float(row.quote_previous_close or 0),"provider":row.quote_provider or "cache",
        "delayed":True,"available":True,"stale":age is None or age>900,
        "updated_at":row.quote_updated_at.isoformat() if row.quote_updated_at else None,
    }


def _persist_quote_analysis(symbol: str, quote: dict) -> None:
    db=SessionLocal()
    try:
        row=db.query(OverseasStock).filter(OverseasStock.symbol==symbol).first()
        if row is None:
            return
        now=datetime.now();analysis=_analysis_from_quote(quote)
        row.quote_price=float(quote.get("price") or 0);row.quote_change=float(quote.get("change") or 0)
        row.quote_change_percent=float(quote.get("change_percent") or 0);row.quote_open=float(quote.get("open") or 0)
        row.quote_high=float(quote.get("high") or 0);row.quote_low=float(quote.get("low") or 0)
        row.quote_previous_close=float(quote.get("previous_close") or 0);row.quote_provider=str(quote.get("provider") or "")
        row.quote_updated_at=now;row.analysis_score=analysis["score"];row.analysis_label=analysis["label"]
        row.analysis_reason=analysis["reason"];row.analysis_coverage=analysis["coverage"];row.analysis_updated_at=now
        row.analysis_components_json=json.dumps(analysis.get("components") or [],ensure_ascii=False,separators=(",",":"))
        commit_or_rollback(db)
    finally:
        db.close()


def _provider(db: Session) -> tuple[str,dict[str,str]]:
    finnhub=get_provider_credentials(PROVIDER_FINNHUB,db)
    if finnhub.get("api_key"):
        return PROVIDER_FINNHUB,finnhub
    alpha=get_provider_credentials(PROVIDER_ALPHA_VANTAGE,db)
    if alpha.get("api_key"):
        return PROVIDER_ALPHA_VANTAGE,alpha
    return "",{}


def _provider_summary(db: Session) -> dict:
    provider,_=_provider(db)
    return {
        "active":provider or "none",
        "ready":bool(provider),
        "finnhub":{**provider_public_status(PROVIDER_FINNHUB,db),"usage":usage_stats(PROVIDER_FINNHUB,db)},
        "alpha_vantage":{**provider_public_status(PROVIDER_ALPHA_VANTAGE,db),"usage":usage_stats(PROVIDER_ALPHA_VANTAGE,db)},
        "sec_edgar":{**provider_public_status(PROVIDER_SEC_EDGAR,db),"usage":usage_stats(PROVIDER_SEC_EDGAR,db)},
    }


async def _quote(symbol: str, db: Session) -> dict:
    symbol=_clean_symbol(symbol)
    cached=_cache_get(f"quote:{symbol}")
    if cached is not None:
        return dict(cached)
    stored=_stored_quote(db.query(OverseasStock).filter(OverseasStock.symbol==symbol).first())
    provider,creds=_provider(db)
    commit_or_rollback(db)
    if not provider:
        if stored is not None:
            return _cache_put(f"quote:{symbol}",stored,60)
        return _cache_put(f"quote:{symbol}",{
            "symbol":symbol,"price":0.0,"change":0.0,"change_percent":0.0,
            "open":0.0,"high":0.0,"low":0.0,"previous_close":0.0,
            "provider":"none","delayed":True,"available":False,
        },60)
    async with httpx.AsyncClient(timeout=15,follow_redirects=True) as client:
        if provider==PROVIDER_FINNHUB:
            response=await tracked_get(
                client,provider,"quote","https://finnhub.io/api/v1/quote",
                stock_code=symbol,params={"symbol":symbol},headers={"X-Finnhub-Token":creds["api_key"]},
            )
            response.raise_for_status();data=response.json()
            price=float(data.get("c") or 0)
            payload={
                "symbol":symbol,"price":price,"change":float(data.get("d") or 0),
                "change_percent":float(data.get("dp") or 0),"open":float(data.get("o") or 0),
                "high":float(data.get("h") or 0),"low":float(data.get("l") or 0),
                "previous_close":float(data.get("pc") or 0),"timestamp":data.get("t"),
                "provider":"finnhub","delayed":True,"available":price>0,
            }
        else:
            response=await tracked_get(
                client,provider,"global-quote","https://www.alphavantage.co/query",
                stock_code=symbol,params={"function":"GLOBAL_QUOTE","symbol":symbol,"apikey":creds["api_key"]},
            )
            response.raise_for_status();raw=response.json();data=raw.get("Global Quote") or {}
            if raw.get("Note") or raw.get("Information"):
                raise HTTPException(429,str(raw.get("Note") or raw.get("Information")))
            price=float(data.get("05. price") or 0)
            pct=str(data.get("10. change percent") or "0").replace("%","")
            payload={
                "symbol":symbol,"price":price,"change":float(data.get("09. change") or 0),
                "change_percent":float(pct or 0),"open":float(data.get("02. open") or 0),
                "high":float(data.get("03. high") or 0),"low":float(data.get("04. low") or 0),
                "previous_close":float(data.get("08. previous close") or 0),
                "provider":"alpha_vantage","delayed":True,"available":price>0,
            }
    if payload.get("available"):
        _persist_quote_analysis(symbol,payload)
        payload["updated_at"]=datetime.now().isoformat()
        payload["stale"]=False
    elif stored is not None:
        payload=stored
    return _cache_put(f"quote:{symbol}",payload,300)


async def _search(query: str, db: Session) -> list[dict]:
    q=str(query or "").strip()
    if not q:
        return US_STOCKS[:12]
    provider,creds=_provider(db)
    commit_or_rollback(db)
    results=[]
    if provider:
        try:
            async with httpx.AsyncClient(timeout=15,follow_redirects=True) as client:
                if provider==PROVIDER_FINNHUB:
                    response=await tracked_get(client,provider,"symbol-search","https://finnhub.io/api/v1/search",params={"q":q},headers={"X-Finnhub-Token":creds["api_key"]})
                    response.raise_for_status()
                    for row in response.json().get("result") or []:
                        symbol=str(row.get("symbol") or "").upper()
                        if re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,14}",symbol) and "." not in symbol:
                            results.append({"symbol":symbol,"name":row.get("description") or symbol,"exchange":"US","sector":""})
                else:
                    response=await tracked_get(client,provider,"symbol-search","https://www.alphavantage.co/query",params={"function":"SYMBOL_SEARCH","keywords":q,"apikey":creds["api_key"]})
                    response.raise_for_status()
                    for row in response.json().get("bestMatches") or []:
                        symbol=str(row.get("1. symbol") or "").upper()
                        region=str(row.get("4. region") or "")
                        if symbol and region.lower() in {"united states","usa","us"}:
                            results.append({"symbol":symbol,"name":row.get("2. name") or symbol,"exchange":region,"sector":""})
        except Exception:
            results=[]
    if not results:
        needle=q.lower()
        results=[row for row in US_STOCKS if needle in row["symbol"].lower() or needle in row["name"].lower()]
    return results[:20]


async def _company_profile(symbol: str, db: Session) -> dict:
    cached=_cache_get(f"profile:{symbol}")
    if cached is not None:return dict(cached)
    provider,creds=_provider(db);commit_or_rollback(db)
    master=db.query(OverseasStock).filter(OverseasStock.symbol==symbol).first()
    fallback=dict(US_STOCK_MAP.get(symbol) or {
        "symbol":symbol,"name":master.name if master else symbol,"sector":"",
        "exchange":master.exchange if master else "US","currency":"USD",
    })
    fallback["name_ko"]=(master.name_ko if master else "") or US_NAME_KO.get(symbol,"")
    if not provider:return fallback
    try:
        async with httpx.AsyncClient(timeout=15,follow_redirects=True) as client:
            if provider==PROVIDER_FINNHUB:
                response=await tracked_get(client,provider,"company-profile","https://finnhub.io/api/v1/stock/profile2",stock_code=symbol,params={"symbol":symbol},headers={"X-Finnhub-Token":creds["api_key"]})
                response.raise_for_status();row=response.json()
                if row:
                    fallback.update({"symbol":symbol,"name":row.get("name") or fallback["name"],"sector":row.get("finnhubIndustry") or fallback.get("sector","") ,"exchange":row.get("exchange") or "US","currency":row.get("currency") or "USD","country":row.get("country") or "US","market_cap":float(row.get("marketCapitalization") or 0),"weburl":row.get("weburl") or "","logo":row.get("logo") or ""})
            else:
                response=await tracked_get(client,provider,"company-overview","https://www.alphavantage.co/query",stock_code=symbol,params={"function":"OVERVIEW","symbol":symbol,"apikey":creds["api_key"]})
                response.raise_for_status();row=response.json()
                if row and not row.get("Information"):
                    fallback.update({"symbol":symbol,"name":row.get("Name") or fallback["name"],"sector":row.get("Sector") or fallback.get("sector","") ,"industry":row.get("Industry") or "","exchange":row.get("Exchange") or "US","currency":row.get("Currency") or "USD","country":row.get("Country") or "US","market_cap":float(row.get("MarketCapitalization") or 0),"description":row.get("Description") or "","pe_ratio":row.get("PERatio"),"pb_ratio":row.get("PriceToBookRatio"),"eps":row.get("EPS"),"dividend_yield":row.get("DividendYield"),"week_52_high":row.get("52WeekHigh"),"week_52_low":row.get("52WeekLow")})
    except Exception:
        pass
    return _cache_put(f"profile:{symbol}",fallback,3600)


async def _sec_filings(symbol: str, db: Session) -> list[dict]:
    creds=get_provider_credentials(PROVIDER_SEC_EDGAR,db)
    contact=str(creds.get("contact") or "").strip()
    if not contact:return []
    cached=_cache_get(f"sec:{symbol}")
    if cached is not None:return list(cached)
    commit_or_rollback(db)
    headers={"User-Agent":f"StockLog/{contact}","Accept-Encoding":"gzip, deflate"}
    try:
        async with httpx.AsyncClient(timeout=20,follow_redirects=True,headers=headers) as client:
            tickers=_cache_get("sec:tickers")
            if tickers is None:
                response=await tracked_get(client,PROVIDER_SEC_EDGAR,"company-tickers","https://www.sec.gov/files/company_tickers.json",request_kind="interactive")
                response.raise_for_status();tickers=response.json();_cache_put("sec:tickers",tickers,86400)
            match=next((row for row in tickers.values() if str(row.get("ticker") or "").upper()==symbol),None)
            if not match:return []
            cik=str(int(match["cik_str"])).zfill(10)
            response=await tracked_get(client,PROVIDER_SEC_EDGAR,"submissions",f"https://data.sec.gov/submissions/CIK{cik}.json",stock_code=symbol)
            response.raise_for_status();recent=(response.json().get("filings") or {}).get("recent") or {}
            items=[]
            forms=recent.get("form") or []
            for index,form in enumerate(forms[:40]):
                if form not in {"10-K","10-Q","8-K","20-F","6-K"}:continue
                accession=(recent.get("accessionNumber") or [""]*len(forms))[index]
                primary=(recent.get("primaryDocument") or [""]*len(forms))[index]
                filed=(recent.get("filingDate") or [""]*len(forms))[index]
                accession_path=str(accession).replace("-","")
                url=f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession_path}/{primary}"
                items.append({"form":form,"filed_at":filed,"title":f"{form} 공시","url":url})
                if len(items)>=8:break
            return _cache_put(f"sec:{symbol}",items,3600)
    except Exception:
        return []


class OverseasOrderIn(BaseModel):
    symbol: str
    side: str
    quantity: int = Field(ge=1,le=100000)


def _account(db: Session,user_id: int) -> OverseasPaperAccount:
    row=db.query(OverseasPaperAccount).filter(OverseasPaperAccount.user_id==user_id).first()
    if row is None:
        row=OverseasPaperAccount(user_id=user_id,starting_cash=100000.0,cash=100000.0)
        db.add(row);commit_or_rollback(db);db.refresh(row)
    return row


@router.get("/status")
def overseas_status(_:User=Depends(current_user),db:Session=Depends(get_db)):
    return {"market":"US","currency":"USD","providers":_provider_summary(db),"universe":_universe_status(db),"paper_trading":True,"live_trading":False,"auto_trading":"analysis_only"}


@router.post("/universe/sync")
async def overseas_universe_sync(_:User=Depends(current_user),db:Session=Depends(get_db)):
    result=await _sync_us_universe(db,force=True)
    return {"ok":bool(result.get("total")),"message":f"미국 상장 종목 {int(result.get('total') or 0):,}개를 확인했습니다.","universe":result}


def _profile_data(user_id: int, db: Session) -> tuple[dict,str,bool]:
    profile=db.query(InvestmentProfile).filter(InvestmentProfile.user_id==user_id).first()
    if profile is None:
        return {},"",False
    try:
        scores=json.loads(profile.scores_json or "{}")
    except (TypeError,ValueError,json.JSONDecodeError):
        scores={}
    return scores if isinstance(scores,dict) else {},str(profile.result_code or ""),True


def _row_analysis(row: OverseasStock, profile_scores: dict, profile_code: str) -> tuple[dict | None,dict]:
    quote=_stored_quote(row)
    try:
        components=json.loads(row.analysis_components_json or "[]")
    except (TypeError,ValueError,json.JSONDecodeError):
        components=[]
    if not isinstance(components,list):
        components=[]
    aggregate=row.analysis_score
    reason=row.analysis_reason or "화면에 표시된 종목부터 무료 API 한도 안에서 분석합니다."
    label=row.analysis_label or "분석 대기"
    coverage=float(row.analysis_coverage or 0)
    if quote and not components:
        rebuilt=_analysis_from_quote(quote)
        aggregate=rebuilt.get("score");label=rebuilt.get("label") or label;reason=rebuilt.get("reason") or reason
        coverage=float(rebuilt.get("coverage") or 0);components=rebuilt.get("components") or []
    user_profile_ready=bool(profile_scores or profile_code)
    profile=profile_score_from_components(
        components,profile_scores=profile_scores,profile_code=profile_code,aggregate_score=aggregate,
    ) if components and user_profile_ready else {
        "score":None,
        "label":"분석 대기" if user_profile_ready else "성향 미검사",
        "traits":[],"components":[],
    }
    public_components=[]
    for raw in profile.get("components") or components:
        if isinstance(raw,dict):
            public_components.append({key:value for key,value in raw.items() if not str(key).startswith("_")})
    best=max((profile.get("traits") or []),key=lambda item:float(item.get("fit") or 0),default=None)
    profile_reason=(
        f"{best.get('label')}: 내 선호와 {float(best.get('fit') or 0):.0f}% 유사"
        if best else (
            "시세 분석이 완료되면 내 투자 성향과의 적합도를 계산합니다."
            if user_profile_ready else "투자성향 검사 후 종목 성격과 비교합니다."
        )
    )
    return quote,{
        "ready":aggregate is not None,"score":round(float(aggregate),1) if aggregate is not None else None,
        "label":label,"reason":reason,"coverage":round(coverage,1),
        "updated_at":row.analysis_updated_at.isoformat() if row.analysis_updated_at else None,
        "components":public_components,"profile_score":profile.get("score"),"profile_label":profile.get("label") or "성향 미검사",
        "profile_reason":profile_reason,"profile_ready":user_profile_ready,
    }


def _smart_stock_payload(row: OverseasStock, profile_scores: dict | None = None, profile_code: str = "") -> dict:
    quote,analysis=_row_analysis(row,profile_scores or {},profile_code)
    age=(datetime.now()-row.quote_updated_at).total_seconds() if row.quote_updated_at else None
    return {
        "symbol":row.symbol,"name":row.name,"name_ko":row.name_ko or US_NAME_KO.get(row.symbol,""),
        "display_name":f"{row.symbol}({row.name_ko or US_NAME_KO.get(row.symbol,'')})" if (row.name_ko or US_NAME_KO.get(row.symbol)) else row.symbol,
        "exchange":row.exchange,"mic":row.mic,
        "currency":row.currency or "USD","asset_type":row.asset_type,"is_etf":bool(row.is_etf),
        "quote":quote or {"symbol":row.symbol,"available":False,"delayed":True,"stale":True},
        "analysis":analysis,
        "data_state":"waiting" if quote is None else "stale" if age is None or age>900 else "fresh",
    }


@router.get("/smart")
async def overseas_smart_list(
    q:str=Query("",max_length=80),exchange:str=Query("all",max_length=30),
    asset_type:str=Query("stock",max_length=20),sort_by:str=Query("analysis_score",max_length=30),
    sort_order:str=Query("desc",max_length=8),page:int=Query(1,ge=1),page_size:int=Query(20,ge=10,le=50),
    refresh:bool=Query(True),u:User=Depends(current_user),db:Session=Depends(get_db),
):
    if asset_type not in {"all","stock","etf"}:
        raise HTTPException(422,"종목 구분은 전체·주식·ETF만 지원합니다.")
    if sort_by not in {"analysis_score","profile_score","change_percent","symbol"} or sort_order not in {"asc","desc"}:
        raise HTTPException(422,"지원하지 않는 해외 종목 정렬 조건입니다.")
    universe=await _sync_us_universe(db)
    _backfill_korean_names(db)
    profile_scores,profile_code,profile_ready=_profile_data(u.id,db)
    query=db.query(OverseasStock).filter(OverseasStock.is_active==True)
    keyword=str(q or "").strip()
    display_query=re.fullmatch(r"([A-Za-z][A-Za-z0-9.\-]{0,14})\s*\([^)]*\)",keyword)
    if display_query:
        keyword=display_query.group(1).upper()
    if keyword:
        pattern=f"%{keyword}%"
        query=query.filter(or_(OverseasStock.symbol.ilike(pattern),OverseasStock.name.ilike(pattern),OverseasStock.name_ko.ilike(pattern)))
    if exchange!="all":
        query=query.filter(OverseasStock.exchange==exchange)
    if asset_type=="stock":
        query=query.filter(OverseasStock.asset_type=="stock")
    elif asset_type=="etf":
        query=query.filter(OverseasStock.is_etf==True)
    total=int(query.count())
    pages=max(1,math.ceil(total/max(1,page_size)));current_page=min(page,pages)
    search_order=[]
    if keyword:
        upper=keyword.upper();lower=keyword.lower()
        search_order=[case(
            (func.upper(OverseasStock.symbol)==upper,0),
            (OverseasStock.name_ko==keyword,1),
            (func.upper(OverseasStock.symbol).like(f"{upper}%"),2),
            (OverseasStock.name_ko.like(f"{keyword}%"),3),
            (func.lower(OverseasStock.name).like(f"{lower}%"),4),
            else_=5,
        )]
    if sort_by=="profile_score":
        candidates=query.order_by(OverseasStock.analysis_score.is_(None),OverseasStock.analysis_score.desc(),OverseasStock.priority.asc(),OverseasStock.symbol.asc()).all()
        def profile_sort_key(row):
            _quote_data,analysis=_row_analysis(row,profile_scores,profile_code)
            value=analysis.get("profile_score")
            numeric=float(value or 0)
            row_symbol=str(row.symbol or "").upper();row_ko=str(row.name_ko or "");row_name=str(row.name or "").lower()
            search_rank=(0 if keyword and row_symbol==keyword.upper() else 1 if keyword and row_ko==keyword else 2 if keyword and row_symbol.startswith(keyword.upper()) else 3 if keyword and row_ko.startswith(keyword) else 4 if keyword and row_name.startswith(keyword.lower()) else 5)
            return (search_rank,value is None,numeric if sort_order=="asc" else -numeric,row.priority,row.symbol)
        candidates.sort(key=profile_sort_key)
        rows=candidates[(current_page-1)*page_size:current_page*page_size]
        ordered=None
    elif sort_by=="symbol":
        order=OverseasStock.symbol.asc() if sort_order=="asc" else OverseasStock.symbol.desc()
        ordered=query.order_by(*search_order,order)
    elif sort_by=="change_percent":
        metric=OverseasStock.quote_change_percent
        order=metric.asc() if sort_order=="asc" else metric.desc()
        ordered=query.order_by(*search_order,metric.is_(None),order,OverseasStock.priority.asc(),OverseasStock.symbol.asc())
    else:
        metric=OverseasStock.analysis_score
        order=metric.asc() if sort_order=="asc" else metric.desc()
        ordered=query.order_by(*search_order,metric.is_(None),order,OverseasStock.priority.asc(),OverseasStock.symbol.asc())
    if ordered is not None:
        rows=ordered.offset((current_page-1)*page_size).limit(page_size).all()
    provider,_creds=_provider(db)
    refresh_limit=min(len(rows),12 if provider==PROVIDER_FINNHUB else 1 if provider==PROVIDER_ALPHA_VANTAGE else 0)
    if refresh and refresh_limit:
        quotes=await asyncio.gather(*[_quote(row.symbol,db) for row in rows[:refresh_limit]],return_exceptions=True)
        quote_map={row.symbol:value for row,value in zip(rows[:refresh_limit],quotes) if isinstance(value,dict)}
        db.expire_all()
        symbols=[row.symbol for row in rows]
        refreshed={row.symbol:row for row in db.query(OverseasStock).filter(OverseasStock.symbol.in_(symbols)).all()}
        rows=[refreshed.get(symbol) for symbol in symbols if refreshed.get(symbol) is not None]
        # A freshly calculated score should be reflected immediately instead of
        # waiting for the next page request, while global pagination remains DB-backed.
        if sort_by=="analysis_score":
            rows.sort(key=lambda row:(row.analysis_score is None,float(row.analysis_score or 0)*(1 if sort_order=="asc" else -1),row.priority,row.symbol))
        elif sort_by=="profile_score":
            def refreshed_profile_key(row):
                _quote_data,analysis=_row_analysis(row,profile_scores,profile_code);value=analysis.get("profile_score")
                return (value is None,float(value or 0)*(1 if sort_order=="asc" else -1),row.priority,row.symbol)
            rows.sort(key=refreshed_profile_key)
        elif sort_by=="change_percent":
            rows.sort(key=lambda row:(row.quote_change_percent is None,float(row.quote_change_percent or 0)*(1 if sort_order=="asc" else -1),row.priority,row.symbol))
    else:
        quote_map={}
    items=[]
    for row in rows:
        payload=_smart_stock_payload(row,profile_scores,profile_code)
        if row.symbol in quote_map:
            payload["quote"]={**payload["quote"],**quote_map[row.symbol]}
        items.append(payload)
    exchanges=[value for (value,) in db.query(OverseasStock.exchange).filter(OverseasStock.is_active==True).distinct().order_by(OverseasStock.exchange).all() if value]
    latest=_universe_status(db)
    return {
        "items":items,"count":len(items),"total":total,"pages":pages,"page":current_page,"page_size":page_size,
        "sort_by":sort_by,"sort_order":sort_order,"filters":{"q":keyword,"exchange":exchange,"asset_type":asset_type},
        "filter_options":{"exchanges":exchanges,"asset_types":["stock","etf"]},
        "universe":{**latest,**({"warning":universe["warning"]} if universe.get("warning") else {})},
        "provider":provider or "none","refresh_limit":refresh_limit,
        "profile":{"ready":profile_ready,"result_code":profile_code or None},
        "analysis_guide":"해외 종합점수는 현재 무료 데이터에서 확인 가능한 주가 흐름·변동성부터 반영합니다. 내 성향 적합도는 종합점수와 별도로 종목 성격과 회원 투자성향을 비교합니다.",
    }


@router.get("/overview")
async def overseas_overview(_:User=Depends(current_user),db:Session=Depends(get_db)):
    provider,_=_provider(db)
    watch=US_STOCKS[:8]
    quotes=[]
    if provider==PROVIDER_FINNHUB:
        quotes=await asyncio.gather(*[_quote(row["symbol"],db) for row in watch],return_exceptions=True)
    elif provider==PROVIDER_ALPHA_VANTAGE:
        quotes=[await _quote(watch[0]["symbol"],db)]
    quote_map={x.get("symbol"):x for x in quotes if isinstance(x,dict)}
    items=[{**row,"quote":quote_map.get(row["symbol"],{})} for row in watch]
    return {"market":"US","currency":"USD","items":items,"sectors":sorted({row["sector"] for row in US_STOCKS}),"providers":_provider_summary(db),"delayed":True}


@router.get("/search")
async def overseas_search(q:str=Query("",max_length=80),_:User=Depends(current_user),db:Session=Depends(get_db)):
    return {"items":await _search(q,db),"query":q}


@router.get("/stocks/{symbol}")
async def overseas_stock_detail(symbol:str,u:User=Depends(current_user),db:Session=Depends(get_db)):
    symbol=_clean_symbol(symbol)
    quote=await _quote(symbol,db)
    profile=await _company_profile(symbol,db)
    filings=await _sec_filings(symbol,db)
    db.expire_all();master=db.query(OverseasStock).filter(OverseasStock.symbol==symbol).first()
    profile_scores,profile_code,_profile_ready=_profile_data(u.id,db)
    smart=_smart_stock_payload(master,profile_scores,profile_code) if master else None
    return {"symbol":symbol,"quote":quote,"profile":profile,"analysis":(smart or {}).get("analysis"),"filings":filings,"currency":"USD","market":"US","providers":_provider_summary(db)}


@router.get("/sectors")
def overseas_sectors(_:User=Depends(current_user)):
    groups={}
    for row in US_STOCKS:
        groups.setdefault(row["sector"],[]).append(row)
    return {"items":[{"name":name,"count":len(rows),"stocks":rows} for name,rows in sorted(groups.items(),key=lambda x:(-len(x[1]),x[0]))]}


@router.get("/paper/portfolio")
async def overseas_paper_portfolio(u:User=Depends(current_user),db:Session=Depends(get_db)):
    account=_account(db,u.id)
    positions=db.query(OverseasPaperPosition).filter(OverseasPaperPosition.user_id==u.id,OverseasPaperPosition.quantity>0).order_by(OverseasPaperPosition.symbol).all()
    commit_or_rollback(db)
    quotes=await asyncio.gather(*[_quote(row.symbol,db) for row in positions],return_exceptions=True)
    holdings=[];evaluation=0.0;purchase=0.0;day_profit=0.0
    for row,quote in zip(positions,quotes):
        q=quote if isinstance(quote,dict) else {};price=float(q.get("price") or row.avg_price);qty=int(row.quantity or 0)
        value=price*qty;cost=float(row.avg_price or 0)*qty;pnl=value-cost;previous=float(q.get("previous_close") or price)
        evaluation+=value;purchase+=cost;day_profit+=(price-previous)*qty
        holdings.append({"symbol":row.symbol,"name":row.name or row.symbol,"quantity":qty,"avg_price":row.avg_price,"current_price":price,"evaluation_amount":round(value,2),"purchase_amount":round(cost,2),"profit_loss":round(pnl,2),"return_rate":round((pnl/cost*100) if cost else 0,2),"day_profit":round((price-previous)*qty,2),"day_return_rate":round(((price-previous)/previous*100) if previous else 0,2),"provider":q.get("provider") or "cache"})
    total=float(account.cash)+evaluation
    return {"account_no":f"US-PAPER-{u.id:04d}","currency":"USD","environment":"mock","summary":{"cash":round(account.cash,2),"buying_power":round(account.cash,2),"buying_power_available":True,"purchase_amount":round(purchase,2),"evaluation_amount":round(evaluation,2),"profit_loss":round(evaluation-purchase,2),"return_rate":round(((evaluation-purchase)/purchase*100) if purchase else 0,2),"day_profit":round(day_profit,2),"day_return_rate":round((day_profit/(evaluation-day_profit)*100) if evaluation-day_profit else 0,2),"total_asset":round(total,2)},"holdings":holdings,"providers":_provider_summary(db)}


@router.get("/paper/orders")
def overseas_paper_orders(u:User=Depends(current_user),db:Session=Depends(get_db)):
    rows=db.query(OverseasPaperOrder).filter(OverseasPaperOrder.user_id==u.id).order_by(OverseasPaperOrder.id.desc()).limit(100).all()
    return {"items":[{"id":x.id,"symbol":x.symbol,"name":x.name,"side":x.side,"quantity":x.quantity,"price":x.price,"amount":x.amount,"status":x.status,"provider":x.provider,"created_at":x.created_at.isoformat()} for x in rows]}


@router.post("/paper/orders")
async def overseas_paper_order(body:OverseasOrderIn,u:User=Depends(current_user),db:Session=Depends(get_db)):
    symbol=_clean_symbol(body.symbol);side=str(body.side or "").strip().lower()
    if side not in {"buy","sell"}:raise HTTPException(422,"매수 또는 매도를 선택해주세요.")
    quote=await _quote(symbol,db);price=float(quote.get("price") or 0)
    if price<=0:raise HTTPException(409,"현재 해외 시세를 확인할 수 없어 주문하지 않았습니다. 관리자 해외 API 설정을 확인해주세요.")
    account=_account(db,u.id)
    position=db.query(OverseasPaperPosition).filter(OverseasPaperPosition.user_id==u.id,OverseasPaperPosition.symbol==symbol).first()
    qty=int(body.quantity);amount=round(price*qty,2);fee=round(amount*0.0005,2)
    name=(await _company_profile(symbol,db)).get("name") or symbol
    if side=="buy":
        total=amount+fee
        if account.cash+1e-9<total:raise HTTPException(400,"해외 모의계좌 주문가능금액이 부족합니다.")
        if position is None:
            position=OverseasPaperPosition(user_id=u.id,symbol=symbol,name=name,quantity=0,avg_price=0);db.add(position)
        old_cost=float(position.avg_price or 0)*int(position.quantity or 0)
        position.quantity=int(position.quantity or 0)+qty;position.avg_price=(old_cost+amount)/position.quantity;position.name=name
        account.cash-=total
    else:
        if position is None or int(position.quantity or 0)<qty:raise HTTPException(400,"매도 가능한 해외 모의 보유수량이 부족합니다.")
        position.quantity-=qty;position.realized_pnl=float(position.realized_pnl or 0)+(price-float(position.avg_price or 0))*qty-fee
        account.cash+=amount-fee
    order=OverseasPaperOrder(user_id=u.id,symbol=symbol,name=name,side=side,quantity=qty,price=price,amount=amount,status="filled",provider=quote.get("provider") or "")
    db.add(order);commit_or_rollback(db);db.refresh(order)
    return {"ok":True,"message":f"{name} {qty}주 해외 모의 {'매수' if side=='buy' else '매도'}가 체결되었습니다.","order":{"id":order.id,"symbol":symbol,"side":side,"quantity":qty,"price":price,"amount":amount,"fee":fee,"status":"filled"}}
