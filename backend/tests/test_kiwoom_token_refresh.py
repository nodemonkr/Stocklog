import asyncio
import time
from datetime import datetime, timedelta, timezone

import httpx

from backend.app.kiwoom import KiwoomRestClient


def _response(payload, status=200):
    request=httpx.Request("POST","https://mockapi.kiwoom.com/api/dostk/chart")
    return httpx.Response(status,json=payload,request=request)


def test_body_level_8005_refreshes_token_and_retries_once():
    async def scenario():
        client=KiwoomRestClient("app","secret")
        client.token="stale-token"
        client._token_valid_until_monotonic=time.monotonic()+3600
        responses=[
            (_response({
                "return_code":3,
                "return_msg":"인증에 실패했습니다[8005:Token이 유효하지 않습니다]",
            }), {"authorization":"Bearer stale-token"}),
            (_response({"return_code":0,"value":"ok"}), {"authorization":"Bearer fresh-token"}),
        ]
        refresh_calls=[]

        async def fake_post(**kwargs):
            return responses.pop(0)

        async def fake_issue_token(force=False, stale_token=None):
            refresh_calls.append((force,stale_token))
            client.token="fresh-token"
            client.token_expires_dt=(datetime.now(timezone.utc)+timedelta(hours=24)).isoformat()
            client._token_valid_until_monotonic=time.monotonic()+3600
            return {"token":"fresh-token","expires_dt":client.token_expires_dt}

        client._await_post_interruptibly=fake_post
        client.issue_token=fake_issue_token
        data,_=await client.call("/api/dostk/chart","ka10060",{"stk_cd":"005930"})
        assert data["value"] == "ok"
        assert refresh_calls == [(True,"stale-token")]
        assert responses == []

    asyncio.run(scenario())


def test_http_401_refreshes_token_and_retries_once():
    async def scenario():
        client=KiwoomRestClient("app","secret")
        client.token="stale-token"
        client._token_valid_until_monotonic=time.monotonic()+3600
        responses=[
            (_response({"message":"unauthorized"}, status=401), {"authorization":"Bearer stale-token"}),
            (_response({"return_code":0,"value":"ok"}), {"authorization":"Bearer fresh-token"}),
        ]
        refresh_calls=[]

        async def fake_post(**kwargs):
            return responses.pop(0)

        async def fake_issue_token(force=False, stale_token=None):
            refresh_calls.append((force,stale_token))
            client.token="fresh-token"
            client._token_valid_until_monotonic=time.monotonic()+3600
            return {"token":"fresh-token"}

        client._await_post_interruptibly=fake_post
        client.issue_token=fake_issue_token
        data,_=await client.call("/api/dostk/chart","ka10060",{})
        assert data["value"] == "ok"
        assert refresh_calls == [(True,"stale-token")]

    asyncio.run(scenario())


def test_expired_cached_token_is_not_considered_valid():
    client=KiwoomRestClient("app","secret")
    client.token="expired"
    client._token_valid_until_monotonic=time.monotonic()-1
    assert client._token_cache_is_valid() is False


def test_parse_compact_kiwoom_expiry_as_korea_time():
    parsed=KiwoomRestClient._parse_token_expiry("20260829083000")
    assert parsed is not None
    assert parsed.tzinfo is not None
    # 08:30 KST == 23:30 UTC on the previous day.
    assert parsed.astimezone(timezone.utc).strftime("%Y%m%d%H%M%S") == "20260828233000"


def test_peer_refresh_prevents_duplicate_token_issuance():
    async def scenario():
        client=KiwoomRestClient("app","secret")
        client.token="new-token"
        client.token_expires_dt=(datetime.now(timezone.utc)+timedelta(hours=23)).isoformat()
        client._token_valid_until_monotonic=time.monotonic()+3600
        result=await client.issue_token(force=True,stale_token="old-token")
        assert result["cached"] is True
        assert result["refreshed_by_peer"] is True
        assert result["token"] == "new-token"

    asyncio.run(scenario())
