import asyncio
import re
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from typing import Any

import httpx


class KiwoomError(RuntimeError):
    pass


def _num(value):
    if value in (None, "", "-", "--"):
        return 0.0
    try:
        return float(
            str(value)
            .replace(",", "")
            .replace("+", "")
            .replace("%", "")
            .strip()
        )
    except Exception:
        return 0.0


def _first(mapping: dict, keys: list[str], default=None):
    for key in keys:
        if key in mapping and mapping[key] not in (None, ""):
            return mapping[key]
    return default


def _normalize_order_side(value):
    raw=str(value or "").strip()
    lower=raw.lower()

    if (
        "매수" in raw
        or lower in ("buy","b")
        or raw in ("2","+2")
    ):
        return "매수"

    if (
        "매도" in raw
        or lower in ("sell","s")
        or raw in ("1","-1")
    ):
        return "매도"

    # 0/3 are frequently order-type values, not buy/sell side.
    if raw in ("0","3",""):
        return ""

    return raw


def _walk_dicts(obj: Any):
    if isinstance(obj, dict):
        yield obj
        for value in obj.values():
            yield from _walk_dicts(value)
    elif isinstance(obj, list):
        for item in obj:
            yield from _walk_dicts(item)


def _walk_lists(obj: Any):
    if isinstance(obj, list):
        yield obj
        for item in obj:
            yield from _walk_lists(item)
    elif isinstance(obj, dict):
        for value in obj.values():
            yield from _walk_lists(value)


class KiwoomRestClient:
    """
    키움 REST API 실전/모의투자 client.

    핵심 제한 대응:
    - 전체 조회 burst 완화
    - 모의투자 동일 TR은 최소 1.10초 간격
    - HTTP 429는 미지원으로 판단하지 않음
    - 429 발생 시 1.25초 대기 후 동일 요청 1회만 재시도
    """

    # Kiwoom official limits (2026-08): domestic query/order 5 req/s per token,
    # and mock accounts additionally limit the same TR to 1 req/s.
    # Keep conservative margins to avoid cascading temporary throttles.
    GLOBAL_MIN_INTERVAL = 0.23
    MOCK_SAME_TR_MIN_INTERVAL = 1.08
    RATE_LIMIT_RETRY_WAIT = 1.50
    MAX_COOLDOWN_SECONDS = 30.0
    # A leaked/cancelled gate must never stall every subsequent Kiwoom call forever.
    # 90s is comfortably above normal HTTP(25s)+cooldown(30s), yet bounded.
    GATE_WAIT_TIMEOUT_SECONDS = 90.0
    # Official Kiwoom REST access tokens are valid for 24 hours. Refresh a few
    # minutes early so a long-running sync never starts with a near-expiry token.
    TOKEN_FALLBACK_LIFETIME_SECONDS = 23 * 60 * 60 + 50 * 60
    TOKEN_EXPIRY_SAFETY_SECONDS = 5 * 60

    _PRIORITY = {
        # Orders first
        "kt10000": 0, "kt10001": 0, "kt10002": 0, "kt10003": 0,
        # executions / balances
        "ka10075": 10, "ka10076": 10, "kt00008": 10, "kt00004": 12,
        # quote/order book
        "ka10004": 20,
        # buying power / cash
        "kt00001": 30,
        # investor-flow history is analytical/background work, below trading/quotes.
        "ka10060": 60,
        # themes are intentionally lowest priority
        "ka90001": 80, "ka90002": 80,
    }

    def __init__(
        self,
        app_key: str,
        secret_key: str,
        use_mock: bool = True,
    ):
        self.app_key = app_key
        self.secret_key = secret_key
        self.use_mock = use_mock
        self.base = (
            "https://mockapi.kiwoom.com"
            if use_mock
            else "https://api.kiwoom.com"
        )

        self.token = None
        self.token_expires_dt = None
        self._token_issued_monotonic = 0.0
        self._token_valid_until_monotonic = 0.0
        self._token_lock = asyncio.Lock()

        self._global_last_request = 0.0
        self._api_last_request: dict[str, float] = {}
        self._request_lock = asyncio.Lock()

        # One broker session per token: serialize HTTP calls through a priority gate.
        self._gate_cond = asyncio.Condition()
        self._gate_queue = []
        self._gate_seq = 0
        self._gate_active = False
        self._gate_active_since = 0.0
        self._gate_active_api_id = ""

        self._cooldown_until = 0.0
        self._cooldown_reason = ""
        self._last_error = ""
        self._last_success_at = None
        self._rate_limit_hits = 0

        self._response_cache = {}
        self._cache_locks = {}
        self.last_theme_cache_stale = False

        self.last_theme_group_pages = 0
        self.last_theme_stock_pages: dict[str, int] = {}


    def _priority_for(self, api_id: str) -> int:
        return int(self._PRIORITY.get(str(api_id or ""), 50))

    async def _acquire_gate(self, api_id: str):
        """Acquire the single-broker-request gate without cancellation leaks.

        Older builds left cancelled waiters in ``_gate_queue`` and could also
        leave ``_gate_active`` stuck forever.  Once that happened every later
        Kiwoom call waited before the HTTP layer, so normal HTTP timeouts never
        fired.  Keep queue membership exception-safe and bound the wait.
        """
        token = object()
        acquired = False
        deadline = time.monotonic() + float(self.GATE_WAIT_TIMEOUT_SECONDS)
        async with self._gate_cond:
            self._gate_seq += 1
            entry = (self._priority_for(api_id), self._gate_seq, token)
            self._gate_queue.append(entry)
            self._gate_queue.sort(key=lambda x: (x[0], x[1]))
            try:
                while self._gate_active or not self._gate_queue or self._gate_queue[0][2] is not token:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise KiwoomError(
                            f"Kiwoom request gate wait timeout: api_id={api_id}, "
                            f"active_api_id={self._gate_active_api_id or '-'}, "
                            f"queued={len(self._gate_queue)}"
                        )
                    try:
                        await asyncio.wait_for(self._gate_cond.wait(), timeout=remaining)
                    except asyncio.TimeoutError as exc:
                        raise KiwoomError(
                            f"Kiwoom request gate wait timeout: api_id={api_id}, "
                            f"active_api_id={self._gate_active_api_id or '-'}, "
                            f"queued={len(self._gate_queue)}"
                        ) from exc
                self._gate_active = True
                self._gate_active_since = time.monotonic()
                self._gate_active_api_id = str(api_id or "")
                self._gate_queue.pop(0)
                acquired = True
            except BaseException:
                if not acquired:
                    self._gate_queue = [x for x in self._gate_queue if x[2] is not token]
                    self._gate_cond.notify_all()
                raise

    async def _release_gate(self):
        async with self._gate_cond:
            self._gate_active = False
            self._gate_active_since = 0.0
            self._gate_active_api_id = ""
            self._gate_cond.notify_all()

    async def _wait_cooldown(self):
        remaining = self._cooldown_until - time.monotonic()
        if remaining > 0:
            await asyncio.sleep(remaining)

    def _mark_rate_limit(self, message: str):
        self._rate_limit_hits = min(self._rate_limit_hits + 1, 6)
        wait = min(self.MAX_COOLDOWN_SECONDS, self.RATE_LIMIT_RETRY_WAIT * (2 ** (self._rate_limit_hits - 1)))
        self._cooldown_until = max(self._cooldown_until, time.monotonic() + wait)
        self._cooldown_reason = message or "키움 호출 제한"
        self._last_error = self._cooldown_reason

    def _mark_success(self):
        self._last_success_at = datetime.now(timezone.utc).isoformat()
        self._last_error = ""
        if self._cooldown_until <= time.monotonic():
            self._cooldown_reason = ""
        self._rate_limit_hits = 0

    def runtime_status(self):
        remaining = max(0.0, self._cooldown_until - time.monotonic())
        if remaining > 0:
            state = "cooldown"
        elif self._last_error and ("401" in self._last_error or "token" in self._last_error.lower() or "인증" in self._last_error):
            state = "auth_error"
        elif self._last_error:
            state = "warning"
        else:
            state = "ok"
        gate_active_seconds = (
            max(0.0, time.monotonic() - self._gate_active_since)
            if self._gate_active and self._gate_active_since
            else 0.0
        )
        token_valid_seconds = max(
            0.0,
            self._token_valid_until_monotonic - time.monotonic(),
        ) if self._token_valid_until_monotonic else 0.0
        return {
            "state": state,
            "cooldown_seconds": round(remaining, 1),
            "last_error": self._last_error,
            "last_success_at": self._last_success_at,
            "token_cached": bool(self.token),
            "token_expires_dt": self.token_expires_dt,
            "token_valid_seconds": round(token_valid_seconds, 1),
            "queued": len(self._gate_queue) + (1 if self._gate_active else 0),
            "gate_active_api_id": self._gate_active_api_id or None,
            "gate_active_seconds": round(gate_active_seconds, 1),
            "gate_wait_timeout_seconds": float(self.GATE_WAIT_TIMEOUT_SECONDS),
            "mock_same_tr_min_interval": self.MOCK_SAME_TR_MIN_INTERVAL,
            "global_min_interval": self.GLOBAL_MIN_INTERVAL,
        }

    async def _cached_value(self, key: str, ttl: float, loader, stale_ttl: float = 0):
        now = time.monotonic()
        cached = self._response_cache.get(key)
        if cached and now - cached[0] <= ttl:
            return cached[1], False
        lock = self._cache_locks.setdefault(key, asyncio.Lock())
        async with lock:
            now = time.monotonic()
            cached = self._response_cache.get(key)
            if cached and now - cached[0] <= ttl:
                return cached[1], False
            try:
                value = await loader()
                self._response_cache[key] = (time.monotonic(), value)
                return value, False
            except Exception:
                if cached and stale_ttl > 0 and now - cached[0] <= stale_ttl:
                    return cached[1], True
                raise

    async def _throttle(self, api_id: str | None = None):
        async with self._request_lock:
            now = time.monotonic()

            global_wait = (
                self.GLOBAL_MIN_INTERVAL
                - (now - self._global_last_request)
            )

            same_tr_wait = 0.0
            if self.use_mock and api_id:
                last = self._api_last_request.get(
                    api_id,
                    0.0,
                )
                same_tr_wait = (
                    self.MOCK_SAME_TR_MIN_INTERVAL
                    - (now - last)
                )

            wait = max(
                0.0,
                global_wait,
                same_tr_wait,
            )

            if wait > 0:
                await asyncio.sleep(wait)

            stamp = time.monotonic()
            self._global_last_request = stamp

            if api_id:
                self._api_last_request[api_id] = stamp

    @staticmethod
    def _parse_token_expiry(value):
        """Parse Kiwoom expires_dt into an aware UTC datetime when possible.

        Kiwoom currently documents ``expires_dt`` but its textual formatting may
        vary by environment/client sample. Naive timestamps are interpreted as
        Korea time because the broker service is Korea-local.
        """
        raw = str(value or "").strip()
        if not raw:
            return None

        parsed = None
        candidates = [raw]
        if raw.endswith("Z"):
            candidates.insert(0, raw[:-1] + "+00:00")
        for candidate in candidates:
            try:
                parsed = datetime.fromisoformat(candidate)
                break
            except Exception:
                pass

        if parsed is None:
            for fmt in (
                "%Y%m%d%H%M%S",
                "%Y-%m-%d %H:%M:%S",
                "%Y/%m/%d %H:%M:%S",
            ):
                try:
                    parsed = datetime.strptime(raw, fmt)
                    break
                except Exception:
                    pass

        if parsed is None:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=ZoneInfo("Asia/Seoul"))
        return parsed.astimezone(timezone.utc)

    def _set_token_expiry(self, expires_dt):
        now_mono = time.monotonic()
        self._token_issued_monotonic = now_mono
        lifetime = float(self.TOKEN_FALLBACK_LIFETIME_SECONDS)
        parsed = self._parse_token_expiry(expires_dt)
        if parsed is not None:
            remaining = (parsed - datetime.now(timezone.utc)).total_seconds()
            if remaining > 0:
                lifetime = max(60.0, remaining - float(self.TOKEN_EXPIRY_SAFETY_SECONDS))
        self._token_valid_until_monotonic = now_mono + lifetime

    def _token_cache_is_valid(self):
        if not self.token:
            return False
        if self._token_valid_until_monotonic:
            return time.monotonic() < self._token_valid_until_monotonic
        # Backward compatibility for clients instantiated before this patch.
        parsed = self._parse_token_expiry(self.token_expires_dt)
        if parsed is not None:
            return (
                parsed - datetime.now(timezone.utc)
            ).total_seconds() > float(self.TOKEN_EXPIRY_SAFETY_SECONDS)
        return False

    @staticmethod
    def _response_auth_failure(response):
        if response.status_code in (401, 403):
            return True, f"HTTP {response.status_code}"
        try:
            data = response.json()
        except Exception:
            data = {}
        if not isinstance(data, dict):
            return False, ""
        code = data.get("return_code")
        msg = str(data.get("return_msg") or "").strip()
        combined = f"{code} {msg}".lower()
        markers = (
            "8005",
            "token이 유효하지",
            "token 이 유효하지",
            "invalid token",
            "token invalid",
            "access token expired",
            "토큰이 유효하지",
        )
        if any(marker in combined for marker in markers):
            return True, msg or f"return_code={code}"
        # Kiwoom's current invalid-token response is return_code=3 with an
        # authentication failure message. Keep this narrow so account/login
        # errors unrelated to OAuth are not blindly retried.
        if str(code) == "3" and "인증에 실패" in msg and "token" in combined:
            return True, msg
        return False, ""

    async def issue_token(self, force=False, stale_token=None):
        async with self._token_lock:
            # Another coroutine may already have refreshed the token while this
            # request was waiting for the lock. Reuse that newer token instead
            # of issuing another one and risking broker-side token churn.
            if (
                stale_token
                and self.token
                and self.token != stale_token
                and self._token_cache_is_valid()
            ):
                return {
                    "token": self.token,
                    "expires_dt": self.token_expires_dt,
                    "cached": True,
                    "refreshed_by_peer": True,
                }

            if self._token_cache_is_valid() and not force:
                return {
                    "token": self.token,
                    "expires_dt": self.token_expires_dt,
                    "cached": True,
                }

            # Never keep handing out a token that is known/assumed expired.
            if force or self.token:
                self.token = None
                self.token_expires_dt = None
                self._token_valid_until_monotonic = 0.0

            await self._wait_cooldown()
            await self._acquire_gate("au10001")
            try:
                await self._throttle("au10001")
                async with httpx.AsyncClient(timeout=20) as client:
                    r = await client.post(
                        f"{self.base}/oauth2/token",
                        json={
                            "grant_type": "client_credentials",
                            "appkey": self.app_key,
                            "secretkey": self.secret_key,
                        },
                    )
            finally:
                await self._release_gate()

            if r.status_code == 429:
                self._mark_rate_limit("HTTP 429: au10001 접근토큰 발급 호출 제한")
                raise KiwoomError("HTTP 429: au10001 접근토큰 발급 호출 제한")

            r.raise_for_status()
            data = r.json()
            if data.get("return_code") not in (0, None):
                msg = str(data.get("return_msg") or "키움 토큰 발급 실패")
                self._last_error = f"au10001: {msg}"
                raise KiwoomError(f"[{data.get('return_code')}]({msg})")

            self.token = data.get("token")
            self.token_expires_dt = data.get("expires_dt")
            if not self.token:
                raise KiwoomError("키움 접근토큰이 응답에 없습니다.")
            self._set_token_expiry(self.token_expires_dt)
            self._mark_success()
            return data

    async def _post_once(
        self,
        *,
        path: str,
        api_id: str,
        body: dict,
        cont_yn: str = "",
        next_key: str = "",
        timeout_seconds: float = 25.0,
    ):
        if not self._token_cache_is_valid():
            stale_token = self.token
            await self.issue_token(
                force=bool(stale_token),
                stale_token=stale_token,
            )

        await self._wait_cooldown()
        await self._acquire_gate(api_id)
        # IMPORTANT: everything after acquisition, including throttle sleep,
        # must be inside the finally.  Cancellation during throttle used to
        # leak the active gate and deadlock all future Kiwoom requests.
        try:
            await self._throttle(api_id)

            headers = {
                "authorization": f"Bearer {self.token}",
                "api-id": api_id,
                "Content-Type": "application/json;charset=UTF-8",
            }

            if cont_yn:
                headers["cont-yn"] = cont_yn

            if next_key:
                headers["next-key"] = next_key

            try:
                async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                    r = await client.post(
                        f"{self.base}{path}",
                        headers=headers,
                        json=body,
                    )
                if r.status_code == 429:
                    self._mark_rate_limit(f"HTTP 429: {api_id} 호출 제한")
                elif r.status_code < 500:
                    self._mark_success()
                return r, headers
            except Exception as exc:
                self._last_error = f"{api_id}: {type(exc).__name__}: {exc}"
                raise
        finally:
            await self._release_gate()

    async def _progress_heartbeat(
        self,
        progress_cb,
        *,
        api_id: str,
        status: str = "heartbeat",
    ):
        if not progress_cb:
            return

        event={
            "status":status,
            "api_id":api_id,
            "silent":True,
        }

        result=progress_cb(event)

        if asyncio.iscoroutine(result):
            await result


    async def _interruptible_wait(
        self,
        seconds: float,
        *,
        api_id: str,
        progress_cb=None,
        step: float = 0.2,
    ):
        remaining=max(
            float(seconds or 0),
            0.0,
        )

        while remaining > 0:
            await self._progress_heartbeat(
                progress_cb,
                api_id=api_id,
            )

            chunk=min(
                step,
                remaining,
            )
            await asyncio.sleep(
                chunk
            )
            remaining-=chunk

        await self._progress_heartbeat(
            progress_cb,
            api_id=api_id,
        )


    async def _await_post_interruptibly(
        self,
        *,
        path: str,
        api_id: str,
        body: dict,
        cont_yn: str,
        next_key: str,
        timeout_seconds: float,
        progress_cb=None,
    ):
        """
        Await _post_once in 0.2s slices.

        If the theme progress callback sees the DB stop flag it raises
        CancelledError. We immediately cancel the in-flight HTTP coroutine,
        rather than waiting for a 10/25 second timeout or retry chain.
        """
        task=asyncio.create_task(
            self._post_once(
                path=path,
                api_id=api_id,
                body=body,
                cont_yn=cont_yn,
                next_key=next_key,
                timeout_seconds=timeout_seconds,
            )
        )

        try:
            while not task.done():
                try:
                    return await asyncio.wait_for(
                        asyncio.shield(task),
                        timeout=0.2,
                    )
                except asyncio.TimeoutError:
                    await self._progress_heartbeat(
                        progress_cb,
                        api_id=api_id,
                    )

            return await task

        except asyncio.CancelledError:
            if not task.done():
                task.cancel()

            try:
                await task
            except BaseException:
                pass

            raise

        except BaseException:
            if not task.done():
                task.cancel()

            try:
                await task
            except BaseException:
                pass

            raise
    async def call(
        self,
        path: str,
        api_id: str,
        body: dict,
        cont_yn: str = "",
        next_key: str = "",
        timeout_seconds: float = 25.0,
        progress_cb=None,
    ):
        r, request_headers = await self._await_post_interruptibly(
            path=path,
            api_id=api_id,
            body=body,
            cont_yn=cont_yn,
            next_key=next_key,
            timeout_seconds=timeout_seconds,
            progress_cb=progress_cb,
        )

        auth_failed, auth_message = self._response_auth_failure(r)
        if auth_failed:
            failed_auth = str(request_headers.get("authorization") or "")
            failed_token = (
                failed_auth[7:] if failed_auth.lower().startswith("bearer ") else self.token
            )
            self._last_error = f"{api_id}: auth: {auth_message}"

            await self._progress_heartbeat(
                progress_cb,
                api_id=api_id,
            )

            await self.issue_token(
                force=True,
                stale_token=failed_token,
            )

            await self._progress_heartbeat(
                progress_cb,
                api_id=api_id,
            )

            # Kiwoom may return HTTP 200 with return_code=3 / 8005 for an
            # invalid token, so retry on both HTTP auth status and body-level
            # token errors. Preserve the caller's original timeout.
            r, _ = await self._await_post_interruptibly(
                path=path,
                api_id=api_id,
                body=body,
                cont_yn=cont_yn,
                next_key=next_key,
                timeout_seconds=timeout_seconds,
                progress_cb=progress_cb,
            )

            auth_failed_again, auth_message_again = self._response_auth_failure(r)
            if auth_failed_again:
                self._last_error = f"{api_id}: auth retry failed: {auth_message_again}"

        if r.status_code == 429:
            if progress_cb:
                event={
                    "status":"rate_limit",
                    "message":
                        f"{api_id} 호출 제한 · "
                        f"{self.RATE_LIMIT_RETRY_WAIT:.2f}초 후 재시도",
                    "wait_seconds":
                        self.RATE_LIMIT_RETRY_WAIT,
                }

                result=progress_cb(
                    event
                )

                if asyncio.iscoroutine(
                    result
                ):
                    await result

            # Interruptible wait: DB stop requests are noticed within 0.2 sec.
            await self._interruptible_wait(
                self.RATE_LIMIT_RETRY_WAIT,
                api_id=api_id,
                progress_cb=progress_cb,
            )

            r, _ = await self._await_post_interruptibly(
                path=path,
                api_id=api_id,
                body=body,
                cont_yn=cont_yn,
                next_key=next_key,
                timeout_seconds=timeout_seconds,
                progress_cb=progress_cb,
            )

            if r.status_code == 429:
                raise KiwoomError(
                    f"HTTP 429: {api_id} 호출 제한 "
                    f"(대기 후 재시도도 제한됨)"
                )

        r.raise_for_status()

        try:
            data=r.json()
        except Exception:
            raise KiwoomError(
                f"{api_id} JSON 응답 파싱 실패: "
                f"HTTP {r.status_code}"
            )

        if data.get("return_code") not in (0, None):
            msg = str(data.get("return_msg") or f"{api_id} 요청 실패")
            if any(x in msg for x in ("제한", "초과", "과다", "잠시 후")):
                self._mark_rate_limit(f"{api_id}: {msg}")
            else:
                self._last_error = f"{api_id}: {msg}"
            raise KiwoomError(f"[{data.get('return_code')}]({msg})")

        return data,r.headers

    async def account_numbers(self):
        data, _ = await self.call(
            "/api/dostk/acnt",
            "ka00001",
            {},
        )

        candidates = []

        acct_no = data.get("acctNo")
        if (
            isinstance(acct_no, (str, int))
            and str(acct_no).strip()
        ):
            candidates.append(
                str(acct_no).strip()
            )

        for d in _walk_dicts(data):
            for key, value in d.items():
                key_l = str(key).lower()

                if (
                    key_l in (
                        "acctno",
                        "acnt_no",
                        "account_no",
                        "acct_no",
                    )
                    or "account" in key_l
                    or "acct" in key_l
                ):
                    if (
                        isinstance(
                            value,
                            (str, int),
                        )
                        and str(value).strip()
                    ):
                        candidates.append(
                            str(value).strip()
                        )

        return [
            x
            for x in dict.fromkeys(candidates)
            if x
        ]

    @staticmethod
    def _first_numeric_field(data: dict, keys: list[str]):
        for row in _walk_dicts(data):
            if not isinstance(row, dict):
                continue
            for key in keys:
                if key in row and row[key] not in (None, ""):
                    return _num(row[key]), key
        return 0.0, ""

    async def current_buying_power(self):
        """
        Return broker-confirmed cash buying power with a short single-flight cache.

        The current Kiwoom account response for kt00001 exposes
        `100stk_ord_alow_amt`, which is the 100% cash-backed stock orderable
        amount and does not require a stock code/price.  Do not use kt00010 for
        the account summary: the current official API index classifies it as a
        margin-rate/quantity query, and blank stock parameters can cause repeated
        failures on mock accounts.
        """
        amount_keys = [
            "100stk_ord_alow_amt",
            "ord_alow_amt_entr",
            "ord_alowa",
            "ord_alow_amt",
            "ord_allow_amt",
            "ord_psbl_amt",
        ]
        cash_keys = ["entr", "d2entra", "d2_entra", "dnca_tot_amt"]

        async def loader():
            # Empirically supported query type first; only one fallback variant.
            result = await self._try_variants(
                "kt00001",
                "/api/dostk/acnt",
                [{"qry_tp": "3"}, {"qry_tp": "2"}],
            )
            if not result.get("ok"):
                raise KiwoomError(
                    "kt00001 주문가능금액 조회 실패: "
                    + "; ".join((result.get("errors") or [])[-2:])
                )
            data = result.get("data") or {}
            amount, field = self._first_numeric_field(data, amount_keys)
            if not field:
                raise KiwoomError("kt00001 응답에 주문가능금액 필드가 없습니다.")
            cash, cash_field = self._first_numeric_field(data, cash_keys)
            return {
                "available": True,
                "amount": max(0.0, float(amount)),
                "cash": float(cash),
                "api_id": "kt00001",
                "field": field,
                "cash_field": cash_field,
                "request_body": result.get("body") or {},
            }

        value, stale = await self._cached_value(
            "buying_power", 10.0, loader, stale_ttl=180.0
        )
        out = dict(value)
        out["stale"] = bool(stale)
        return out

    @staticmethod
    def _investor_row(data: dict):
        rows = data.get("stk_invsr_orgn_chart") if isinstance(data, dict) else None
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, dict):
                    return row
        for row in _walk_dicts(data):
            if isinstance(row, dict) and (
                "frgnr_invsr" in row or "orgn" in row or "fnnc_invt" in row
            ):
                return row
        return {}

    @staticmethod
    def _investor_values(row: dict):
        fields = {
            "foreign": "frgnr_invsr",
            "institution": "orgn",
            "financial_investment": "fnnc_invt",
            "investment_trust": "invtrt",
            "pension_etc": "penfnd_etc",
            "insurance": "insrnc",
            "bank": "bank",
            "private_equity": "samo_fund",
            "other_finance": "etc_fnnc",
            "other_corp": "etc_corp",
            "individual": "ind_invsr",
            "national_local": "natn",
            "foreign_other": "natfor",
        }
        return {name: abs(_num(row.get(key))) for name, key in fields.items()}

    async def stock_investor_trades(self, stock_code: str, date_yyyymmdd: str):
        """Today's investor-category buy/sell quantities from actual Kiwoom data."""
        if not re.fullmatch(r"\d{6}", str(stock_code or "")):
            raise KiwoomError("올바른 국내 종목코드가 아닙니다.")
        sides = {}
        rows = {}
        for side, trde_tp in (("buy", "1"), ("sell", "2")):
            data, _ = await self.call(
                "/api/dostk/chart",
                "ka10060",
                {
                    "dt": str(date_yyyymmdd),
                    "stk_cd": str(stock_code),
                    "amt_qty_tp": "2",
                    "trde_tp": trde_tp,
                    "unit_tp": "1",
                },
            )
            row = self._investor_row(data)
            if not row:
                raise KiwoomError(f"ka10060 {side} 투자자별 데이터가 없습니다.")
            rows[side] = row
            sides[side] = self._investor_values(row)

        categories = {}
        all_names = set(sides.get("buy", {})) | set(sides.get("sell", {}))
        for name in all_names:
            buy = float(sides.get("buy", {}).get(name, 0) or 0)
            sell = float(sides.get("sell", {}).get(name, 0) or 0)
            categories[name] = {
                "buy": buy,
                "sell": sell,
                "net": buy - sell,
            }

        actual_date = str(
            (rows.get("buy") or rows.get("sell") or {}).get("dt")
            or date_yyyymmdd
        ).replace("-", "")[:8]
        return {
            "date": actual_date,
            "unit": "shares",
            "categories": categories,
            "source": "kiwoom-ka10060",
        }

    async def stock_investor_history(self, stock_code: str, date_yyyymmdd: str, history_days: int = 20):
        """Return multi-day net investor flow with one ka10060 request.

        Kiwoom ka10060 returns ``stk_invsr_orgn_chart`` as a date-series.  Using
        ``trde_tp=0`` (net buy) and ``amt_qty_tp=2`` (quantity) avoids issuing
        separate buy/sell requests for every date and is therefore suitable for
        StockLog's DB-backed ranking collector.  Values are stored as shares.
        """
        if not re.fullmatch(r"\d{6}", str(stock_code or "")):
            raise KiwoomError("올바른 국내 종목코드가 아닙니다.")
        history_days=max(1,min(int(history_days or 20),60))
        data, _ = await self.call(
            "/api/dostk/chart",
            "ka10060",
            {
                "dt": str(date_yyyymmdd),
                "stk_cd": str(stock_code),
                "amt_qty_tp": "2",
                "trde_tp": "0",
                "unit_tp": "1",
            },
        )
        rows=data.get("stk_invsr_orgn_chart")
        if not isinstance(rows,list):
            rows=[]
        result=[]
        for row in rows:
            if not isinstance(row,dict):
                continue
            raw_date=str(row.get("dt") or "").replace("-","")[:8]
            if not re.fullmatch(r"\d{8}",raw_date):
                continue
            result.append({
                "date":raw_date,
                "close_price":abs(_num(row.get("cur_prc"))),
                "price_change":_num(row.get("pred_pre")),
                "trading_value":abs(_num(row.get("acc_trde_prica"))),
                "individual":_num(row.get("ind_invsr")),
                "foreign":_num(row.get("frgnr_invsr")),
                "institution":_num(row.get("orgn")),
                "financial_investment":_num(row.get("fnnc_invt")),
                "insurance":_num(row.get("insrnc")),
                "investment_trust":_num(row.get("invtrt")),
                "other_finance":_num(row.get("etc_fnnc")),
                "bank":_num(row.get("bank")),
                "pension":_num(row.get("penfnd_etc")),
                "private_equity":_num(row.get("samo_fund")),
                "national":_num(row.get("natn")),
                "other_corp":_num(row.get("etc_corp")),
                "foreign_other":_num(row.get("natfor")),
            })
            if len(result)>=history_days:
                break
        if not result:
            raise KiwoomError("ka10060 투자자 수급 이력 데이터가 없습니다.")
        return {
            "rows":result,
            "unit":"shares",
            "source":"kiwoom-ka10060",
        }

    async def _try_variants(
        self,
        api_id: str,
        path: str,
        bodies: list[dict],
    ):
        errors = []
        rate_limited = False

        for body in bodies:
            try:
                data, headers = await self.call(
                    path,
                    api_id,
                    body,
                )

                return {
                    "ok": True,
                    "api_id": api_id,
                    "body": body,
                    "data": data,
                    "headers": dict(headers),
                    "rate_limited": False,
                }

            except Exception as e:
                msg = str(e)
                errors.append(msg)

                if "HTTP 429" in msg:
                    rate_limited = True

                    # 같은 TR의 다음 variant를 바로 때리지 않음.
                    # 이미 call() 내부 재시도까지 실패했으므로
                    # 이 TR은 이번 probe에서는 종료.
                    break

        return {
            "ok": False,
            "api_id": api_id,
            "errors": errors,
            "rate_limited": rate_limited,
        }

    async def probe_account_trs(self):
        """
        v3.9:
        사용자의 실제 키움 mock 계정에서 성공 확인된 TR을 핵심 동기화 TR로 고정합니다.

        현재 키움 REST API의 계좌 TR 의미를 그대로 사용합니다.

        핵심 TR:
        - kt00003 추정자산조회 (총자산 기준)
        - kt00004 계좌평가현황 (보유/평가/P&L 기준)
        - ka10076 체결
        - ka10075 미체결

        보조 TR:
        - kt00001 예수금상세현황 / 주문가능금액
        - ka10085 계좌수익률
        - ka10170 당일매매일지

        ka10077은 당일실현손익상세이며 stk_cd가 필요한 종목 단위 TR이므로
        계좌 전체 스냅샷 probe에서 호출하지 않습니다.
        """
        core_candidates = [
            (
                "kt00003",
                "/api/dostk/acnt",
                [
                    {"qry_tp": "0"},
                    {"qry_tp": "1"},
                ],
            ),
            (
                "kt00004",
                "/api/dostk/acnt",
                [
                    {"qry_tp": "0", "dmst_stex_tp": "KRX"},
                    {"qry_tp": "1", "dmst_stex_tp": "KRX"},
                ],
            ),
            (
                "ka10076",
                "/api/dostk/acnt",
                [
                    {
                        "qry_tp": "0",
                        "sell_tp": "0",
                        "stex_tp": "0",
                    },
                    {
                        "qry_tp": "0",
                        "sell_tp": "0",
                        "dmst_stex_tp": "KRX",
                    },
                ],
            ),
            (
                "ka10075",
                "/api/dostk/acnt",
                [
                    {
                        "all_stk_tp": "0",
                        "trde_tp": "0",
                        "stex_tp": "0",
                    },
                ],
            ),
        ]

        # 이 둘은 계좌 핵심 데이터가 이미 성공한 상태에서 부가정보 보강용입니다.
        # 실패해도 전체 계좌 동기화를 실패 처리하지 않습니다.
        optional_candidates = [
            (
                "kt00001",
                "/api/dostk/acnt",
                [
                    {"qry_tp": "3"},
                    {"qry_tp": "2"},
                ],
            ),
            (
                "ka10085",
                "/api/dostk/acnt",
                [
                    {"stex_tp": "0"},
                    {"stex_tp": "1"},
                ],
            ),
            (
                "ka10170",
                "/api/dostk/acnt",
                [
                    {
                        "ottks_tp": "01",
                        "ch_crd_tp": "0",
                        "stk_cd": "",
                    },
                    {
                        "ottks_tp": "01",
                        "ch_crd_tp": "1",
                        "stk_cd": "",
                    },
                ],
            ),
        ]

        results = []

        for api_id, path, bodies in core_candidates:
            result = await self._try_variants(
                api_id,
                path,
                bodies,
            )
            result["tier"] = "core"
            results.append(result)
            await asyncio.sleep(0.08)

        for api_id, path, bodies in optional_candidates:
            result = await self._try_variants(
                api_id,
                path,
                bodies,
            )
            result["tier"] = "optional"
            results.append(result)
            await asyncio.sleep(0.08)

        return results
    def normalize_snapshot(
        self,
        probe_results: list[dict],
        account_no: str = "",
    ):
        successful = [
            x
            for x in probe_results
            if x.get("ok")
        ]

        all_dicts = []

        for result in successful:
            all_dicts.extend(
                list(
                    _walk_dicts(
                        result["data"]
                    )
                )
            )

        cash_keys = [
            "entr",
            "dnca_tot_amt",
            "cash",
            "d2_entra",
            "d2_deposit",
        ]

        # Explicit order-available amount fields only.
        # Never substitute plain deposit/entr for this value.
        buying_power_keys = [
            # Generic order-available fields.
            "ord_alow_amt",
            "ord_allow_amt",
            "ord_psbl_amt",
            "ord_psbl_cash",
            "ord_alow_cash",
            "orderable_cash",
            "orderable_amount",
            "ord_psbl_money",
            "ord_alowa",

            # Cash-order fields seen in account response families.
            "ch_ord_alow_amt",
            "ch_ord_allow_amt",
            "ch_ord_psbl_amt",
            "ch_ord_psbl_cash",
            "cash_ord_alow_amt",
            "cash_ord_allow_amt",
            "cash_ord_psbl_amt",
            "cash_ord_psbl_cash",

            # 100% margin / fully cash-backed order amount is the safest
            # stock-independent amount when a generic cash value is absent.
            "ord_alow_amt_100",
            "ord_allow_amt_100",
            "ord_psbl_amt_100",
            "ch_ord_alow_amt_100",
            "ch_ord_psbl_amt_100",
            "cash_ord_alow_amt_100",
            "cash_ord_psbl_amt_100",
            "100stk_ord_alow_amt",
            "profa_100ord_alow_amt",

            # Other margin-rate fields remain last-resort explicit aliases.
            "ord_psbl_amt_40",
            "ord_psbl_amt_30",
            "ord_psbl_amt_20",
            "ord_psbl_amt_10",
        ]

        total_asset_keys = [
            "tot_est_amt",
            "tot_evlt_amt",
            "tot_evltv_amt",
            "tot_aset_amt",
            "total_asset",
            "asset_total",
        ]

        purchase_keys = [
            "tot_pur_amt",
            "tot_buy_amt",
            "purchase_amount",
        ]

        evaluation_keys = [
            "tot_evlt_amt",
            "tot_est_amt",
            "evaluation_amount",
            "tot_evltv_amt",
        ]

        pnl_keys = [
            "tot_evlt_pl",
            "evltv_prft",
            "tot_prft",
            "profit_loss",
            "pl_amt",
        ]

        rate_keys = [
            "tot_prft_rt",
            "prft_rt",
            "return_rate",
            "pl_rt",
        ]

        def search_number(keys):
            for d in all_dicts:
                for key in keys:
                    if (
                        key in d
                        and d[key] not in (
                            None,
                            "",
                        )
                    ):
                        return _num(
                            d[key]
                        )
            return 0.0

        holdings = []
        seen_holdings = set()

        code_keys = [
            "stk_cd",
            "stk_code",
            "code",
            "stock_code",
            "item_cd",
        ]

        name_keys = [
            "stk_nm",
            "stk_name",
            "name",
            "stock_name",
            "item_nm",
        ]

        qty_keys = [
            "rmnd_qty",
            "hold_qty",
            "qty",
            "hldg_qty",
            "poss_qty",
            "cur_qty",
            "sell_alowq",
        ]

        avg_keys = [
            "avg_prc",
            "pur_pric",
            "buy_price",
            "avg_price",
            "pchs_avg_pric",
            "book_uv",
        ]

        current_keys = [
            "cur_prc",
            "cur_price",
            "price",
            "now_prc",
            "now_pric",
            "prpr",
        ]

        item_purchase_keys = [
            "pur_amt",
            "pchs_amt",
            "prch_amt",
            "buy_amt",
            "purchase_amount",
            "book_amt",
        ]

        item_evaluation_keys = [
            "evlt_amt",
            "evltv_amt",
            "evaluation_amount",
            "evlt_amt_krw",
        ]

        item_pnl_keys = [
            "pl_amt",
            "evltv_prft",
            "profit",
            "evlt_pl",
            "evltv_prft_amt",
            "pl_amt_krw",
        ]

        item_rate_keys = [
            "prft_rt",
            "pl_rt",
            "profit_rate",
            "evltv_prft_rt",
        ]

        # Orders and balances are intentionally isolated.
        #
        # ka10075: unfilled orders
        # ka10076: executions
        # kt00007/kt00009: order/execution detail/status (optional families)
        #
        # An order row can contain a stock code and quantity, but that does not
        # make it a holding. The old generic scan could therefore show an unfilled
        # buy as if it were already owned.
        #
        # Holdings are accepted only from balance/evaluation APIs. The first source
        # returning real six-digit stock balance rows wins.
        # Account evaluation is the canonical source for valuation/P&L.
        # Current Kiwoom REST mapping: ka10085 is account return rate and
        # ka10088 is split-order detail.  kt00004 is the canonical account
        # evaluation source; ka10085 is only a secondary holding/P&L fallback.
        holding_source_priority = (
            "kt00004",
            "ka10085",
        )

        successful_by_api = {
            str(result.get("api_id") or ""): result
            for result in successful
        }

        def parse_holding_source(result):
            parsed = []
            local_seen = set()

            if not result:
                return parsed

            for arr in _walk_lists(
                result.get("data")
            ):
                for row in arr:
                    if not isinstance(row,dict):
                        continue

                    code = str(
                        _first(
                            row,
                            code_keys,
                            "",
                        )
                        or ""
                    ).strip()

                    if code.startswith("A"):
                        code=code[1:]

                    if not re.fullmatch(r"\d{6}",code):
                        continue

                    qty = _num(
                        _first(
                            row,
                            qty_keys,
                            0,
                        )
                    )

                    if qty <= 0:
                        continue

                    if code in local_seen:
                        continue

                    local_seen.add(code)

                    name = _first(
                        row,
                        name_keys,
                        "",
                    )

                    avg = abs(
                        _num(
                            _first(
                                row,
                                avg_keys,
                                0,
                            )
                        )
                    )

                    cur = abs(
                        _num(
                            _first(
                                row,
                                current_keys,
                                0,
                            )
                        )
                    )

                    purchase = abs(_num(_first(row,item_purchase_keys,0)))
                    evaluation = abs(_num(_first(row,item_evaluation_keys,0)))
                    pnl = _num(_first(row,item_pnl_keys,0))
                    rate = _num(_first(row,item_rate_keys,0))

                    # Preserve broker fields independently.  The portfolio
                    # reconciliation layer can then verify that P/L belongs to
                    # the same quantity/price row instead of blindly mixing a
                    # value from another account TR.
                    if purchase <= 0 and avg > 0 and qty > 0:
                        purchase = avg * qty
                    if evaluation <= 0 and cur > 0 and qty > 0:
                        evaluation = cur * qty

                    parsed.append(
                        {
                            "code":code,
                            "name":str(name or ""),
                            "quantity":qty,
                            "avg_price":avg,
                            "current_price":cur,
                            "purchase_amount":purchase,
                            "evaluation_amount":evaluation,
                            "profit_loss":pnl,
                            "return_rate":rate,
                            "broker_profit_loss":pnl,
                            "broker_return_rate":rate,
                            "source_tr":result.get("api_id"),
                        }
                    )

            return parsed

        for source_api in holding_source_priority:
            source_holdings=parse_holding_source(
                successful_by_api.get(source_api)
            )

            if source_holdings:
                holdings=source_holdings
                seen_holdings={
                    h["code"]
                    for h in holdings
                }
                break


        orders = []
        seen_orders = set()

        order_no_keys = [
            "ord_no",
            "ordNo",
            "order_no",
        ]

        order_qty_keys = [
            "ord_qty",
            "order_qty",
            "qty",
        ]

        fill_qty_keys = [
            "cntr_qty",
            "filled_qty",
            "cheg_qty",
        ]

        # Execution price must win over order price.  Market orders expose
        # ord_prc/ord_uv as 0 while ka10076 returns the actual fill in
        # cntr_pric and kt00007/kt00009 use cntr_uv.
        order_price_keys = [
            "cntr_pric",
            "cntr_uv",
            "cntr_prc",
            "fill_price",
            "ord_prc",
            "ord_uv",
            "order_price",
        ]

        side_keys = [
            "io_tp_nm",
            "sell_tp",
            "side",
            "order_side",
            "bs_tp",
            "trde_tp",
            "order_type_name",
        ]

        time_keys = [
            "cntr_tm",
            "ord_tm",
            "tm",
            "time",
            "order_time",
        ]

        for result in successful:
            if result["api_id"] not in (
                "ka10076",
                "ka10075",
                "kt00007",
                "kt00009",
            ):
                continue

            for arr in _walk_lists(
                result["data"]
            ):
                for row in arr:
                    if not isinstance(
                        row,
                        dict,
                    ):
                        continue

                    order_no = _first(
                        row,
                        order_no_keys,
                        "",
                    )

                    code = _first(
                        row,
                        code_keys,
                        "",
                    )

                    name = _first(
                        row,
                        name_keys,
                        "",
                    )

                    # A normal order/execution record must have an order
                    # number. This prevents generic stock/balance rows from
                    # appearing in order history.
                    if not str(
                        order_no
                        or ""
                    ).strip():
                        continue

                    key = (
                        str(order_no),
                        str(code),
                        str(
                            _first(
                                row,
                                time_keys,
                                "",
                            )
                        ),
                    )

                    if key in seen_orders:
                        continue

                    seen_orders.add(
                        key
                    )

                    orders.append(
                        {
                            "order_no": str(order_no),
                            "code": (
                                str(code)
                                .replace(
                                    "A",
                                    "",
                                    1,
                                )
                            ),
                            "name": str(name),
                            "side": _normalize_order_side(
                                _first(
                                    row,
                                    side_keys,
                                    "",
                                )
                            ),
                            "order_qty": _num(
                                _first(
                                    row,
                                    order_qty_keys,
                                    0,
                                )
                            ),
                            "filled_qty": _num(
                                _first(
                                    row,
                                    fill_qty_keys,
                                    0,
                                )
                            ),
                            "price": abs(
                                _num(
                                    _first(
                                        row,
                                        order_price_keys,
                                        0,
                                    )
                                )
                            ),
                            "time": str(
                                _first(
                                    row,
                                    time_keys,
                                    "",
                                )
                            ),
                            "source_tr": result["api_id"],
                        }
                    )

        # v3.29.3: account totals must come from account-summary TRs, not
        # from the first matching key found anywhere across all TR payloads.
        # In particular, `tot_evlt_amt` is an evaluation amount and must not
        # be mistaken for total account assets.
        result_dicts = {
            result["api_id"]: list(_walk_dicts(result["data"]))
            for result in successful
        }

        def source_number(api_ids, keys):
            for api_id in api_ids:
                for row in result_dicts.get(api_id, []):
                    for key in keys:
                        if key in row and row[key] not in (None, ""):
                            value = _num(row[key])
                            return value, api_id, key
            return 0.0, "", ""

        def source_number_root(api_ids, keys):
            """Read account-summary fields only from the TR root object.

            Several Kiwoom account TRs reuse names such as ``pl_amt`` /
            ``pl_rt`` inside each holding row.  Walking every nested dict can
            therefore mistake the first stock's P/L for the account summary.
            Headline portfolio numbers must come from the broker's top-level
            account row exactly as displayed in 영웅문.
            """
            by_api={str(x.get("api_id") or ""):x for x in successful}
            for api_id in api_ids:
                result=by_api.get(api_id) or {}
                data=result.get("data")
                roots=[]
                if isinstance(data,dict):
                    roots.append(data)
                    # Some gateways wrap the response once.  Only inspect
                    # direct dict children, never list/holding rows.
                    roots.extend(v for v in data.values() if isinstance(v,dict))
                for row in roots:
                    for key in keys:
                        if key in row and row[key] not in (None, ""):
                            return _num(row[key]), api_id, key
            return 0.0, "", ""


        def semantic_buying_power(api_ids):
            """
            Find a broker-reported order-available AMOUNT even when Kiwoom
            uses an account-response field name not covered by our aliases.

            Safety rules:
            - only fields whose key itself means order + possible/allowed
            - must be amount/cash/money-like
            - never quantity, price, fee, tax, P/L, withdraw-only fields
            - kt00001 and account-summary responses are searched first
            - no calculation from deposit, total assets, or holdings
            """
            candidates = []

            reject_tokens = (
                "qty",
                "cnt",
                "count",
                "prc",
                "price",
                "fee",
                "tax",
                "pl_",
                "profit",
                "loss",
                "wthd",
                "withdraw",
                "loan",
            )

            possibility_tokens = (
                "alow",
                "allow",
                "psbl",
                "possible",
                "avail",
                "able",
            )

            amount_tokens = (
                "amt",
                "cash",
                "money",
            )

            for api_rank, api_id in enumerate(api_ids):
                for row in result_dicts.get(api_id, []):
                    if not isinstance(row, dict):
                        continue

                    for raw_key, raw_value in row.items():
                        if raw_value in (None, ""):
                            continue

                        key = str(raw_key or "").strip().lower()

                        if not key:
                            continue

                        if "ord" not in key and "order" not in key:
                            continue

                        if not any(token in key for token in possibility_tokens):
                            continue

                        if not any(token in key for token in amount_tokens):
                            continue

                        if any(token in key for token in reject_tokens):
                            continue

                        value = _num(raw_value)

                        # Actual broker amount can legitimately be exactly 0.
                        if value < 0:
                            continue

                        score = 100 - api_rank * 20

                        # Generic/cash-backed fields are preferable.
                        if "cash" in key or key.startswith("ch_"):
                            score += 25

                        # 100% margin amount is a safe stock-independent
                        # fallback compared with lower margin-rate amounts.
                        if "100" in key:
                            score += 20

                        # Generic amount with no margin percentage is best.
                        if not any(
                            rate in key
                            for rate in ("10", "20", "30", "40", "50", "60", "100")
                        ):
                            score += 30

                        candidates.append(
                            (
                                score,
                                value,
                                api_id,
                                str(raw_key),
                            )
                        )

            if not candidates:
                return 0.0, "", "", []

            candidates.sort(
                key=lambda x: x[0],
                reverse=True,
            )

            best = candidates[0]

            # Diagnostics expose field names only, never raw account values.
            candidate_names = [
                f"{api_id}:{field}"
                for _, _, api_id, field in candidates[:12]
            ]

            return (
                best[1],
                best[2],
                best[3],
                candidate_names,
            )



        # v3.75.17: StockLog portfolio headline must mirror Kiwoom's
        # kt00004 account summary one-for-one.  These fields live at the TR
        # root and MUST NOT be discovered by recursively walking holding rows.
        #
        # kt00004 semantics (영웅문 계좌평가현황):
        #   entr                 예수금
        #   tot_est_amt          유가잔고평가액 / 총평가
        #   tot_pur_amt          총매입
        #   prsm_dpst_aset_amt   추정예탁자산 / 총 자산
        #   tdy_lspft            당일투자손익
        #   tdy_lspft_rt         당일손익율
        #   lspft                누적투자손익 / 총손익
        #   lspft_rt             누적손익율 / 총수익률
        total_asset, total_asset_tr, total_asset_key = source_number_root(
            ["kt00004", "kt00003"],
            ["prsm_dpst_aset_amt", "prsm_dpst_asset_amt", "tot_aset_amt"],
        )

        cash, cash_tr, cash_key = source_number_root(
            ["kt00004", "kt00001", "kt00003"],
            ["entr", "d2_entra", "dnca_tot_amt", "d2_deposit", "cash"],
        )

        # Orderable cash remains sourced from the dedicated deposit/order TR.
        buying_power, buying_power_tr, buying_power_key = source_number(
            ["kt00001", "kt00003", "kt00004"],
            buying_power_keys,
        )

        buying_power_candidate_keys=[]
        if not buying_power_key:
            (
                buying_power,
                buying_power_tr,
                buying_power_key,
                buying_power_candidate_keys,
            )=semantic_buying_power(["kt00001", "kt00003", "kt00004"])

        buying_power_available=bool(buying_power_key)

        purchase_amount, purchase_tr, purchase_key = source_number_root(
            ["kt00004", "kt00018", "ka10085"],
            ["tot_pur_amt", "tot_prch_amt", "tot_buy_amt"],
        )

        evaluation_amount, evaluation_tr, evaluation_key = source_number_root(
            ["kt00004", "kt00018", "ka10085"],
            ["tot_est_amt", "tot_evlt_amt", "tot_evltv_amt"],
        )

        # IMPORTANT: kt00004's headline '총손익/총수익률' is lspft/lspft_rt.
        # Do not replace it with the sum of per-position pl_amt/pl_rt.  Realized
        # same-day P/L and broker cost semantics make those values legitimately
        # different, as seen in the Kiwoom mock UI.
        profit_loss, profit_tr, profit_key = source_number_root(
            ["kt00004"],
            ["lspft"],
        )
        return_rate, return_tr, return_key = source_number_root(
            ["kt00004"],
            ["lspft_rt"],
        )

        day_profit, day_profit_tr, day_profit_key = source_number_root(
            ["kt00004"],
            ["tdy_lspft"],
        )
        day_return_rate, day_return_tr, day_return_key = source_number_root(
            ["kt00004"],
            ["tdy_lspft_rt"],
        )

        if not evaluation_amount and holdings:
            evaluation_amount = sum(
                float(h.get("evaluation_amount") or 0)
                or (float(h.get("current_price") or 0) * float(h.get("quantity") or 0))
                for h in holdings
            )

        if not purchase_amount and holdings:
            purchase_amount = sum(
                float(h.get("purchase_amount") or 0)
                or (float(h.get("avg_price") or 0) * float(h.get("quantity") or 0))
                for h in holdings
            )

        if not profit_loss and holdings:
            # kt00004 per-stock pl_amt already reflects the broker's account
            # cost model.  Zero is a valid broker P/L and must not fall back to
            # a gross current-minus-average calculation.
            profit_loss = sum(float(h.get("profit_loss") or 0) for h in holdings)

        # Do not manufacture total assets from entr + securities valuation.
        # Same-day buys are unsettled and that addition double-counts capital.
        # If Kiwoom does not provide prsm_dpst_aset_amt, keep total_asset at 0
        # so the caller can label the value as unavailable rather than wrong.

        if (
            not return_rate
            and purchase_amount
        ):
            return_rate = (
                profit_loss
                / purchase_amount
                * 100
            )

        rate_limited = [
            {
                "api_id": x.get("api_id"),
                "errors": x.get(
                    "errors",
                    [],
                ),
            }
            for x in probe_results
            if (
                not x.get("ok")
                and x.get("rate_limited")
            )
        ]

        unsupported_or_failed = [
            {
                "api_id": x.get("api_id"),
                "errors": x.get(
                    "errors",
                    [],
                ),
            }
            for x in probe_results
            if (
                not x.get("ok")
                and not x.get("rate_limited")
            )
        ]

        core_supported = [
            x["api_id"]
            for x in successful
            if x.get("tier") == "core"
        ]

        optional_supported = [
            x["api_id"]
            for x in successful
            if x.get("tier") == "optional"
        ]

        core_failed = [
            item
            for item in unsupported_or_failed
            if next(
                (
                    x.get("tier")
                    for x in probe_results
                    if x.get("api_id") == item.get("api_id")
                ),
                None,
            ) == "core"
        ]

        optional_failed = [
            item
            for item in unsupported_or_failed
            if next(
                (
                    x.get("tier")
                    for x in probe_results
                    if x.get("api_id") == item.get("api_id")
                ),
                None,
            ) == "optional"
        ]

        diagnostics = {
            "supported_trs": [
                x["api_id"]
                for x in successful
            ],
            "core_supported_trs": core_supported,
            "optional_supported_trs": optional_supported,
            "rate_limited_trs": rate_limited,
            "failed_trs": unsupported_or_failed,
            "core_failed_trs": core_failed,
            "optional_failed_trs": optional_failed,
            "removed_mock_unsupported_trs": [
                "kt00016",
                "kt00002",
                "kt00005",
            ],
            "successful_request_bodies": {
                x["api_id"]: x.get(
                    "body",
                    {},
                )
                for x in successful
            },
            "summary_sources": {
                "total_asset": {
                    "tr": total_asset_tr,
                    "field": total_asset_key,
                    "value": round(total_asset, 2),
                },
                "cash": {
                    "tr": cash_tr,
                    "field": cash_key,
                    "value": round(cash, 2),
                },
                "buying_power": {
                    "tr": buying_power_tr,
                    "field": buying_power_key,
                    "value": round(buying_power, 2),
                    "available": buying_power_available,
                    "semantic_candidates": buying_power_candidate_keys,
                    "dedicated_tr_success": bool(
                        result_dicts.get("kt00001")
                        or result_dicts.get("kt00001")
                    ),
                },
                "purchase_amount": {
                    "tr": purchase_tr,
                    "field": purchase_key,
                    "value": round(purchase_amount, 2),
                },
                "evaluation_amount": {
                    "tr": evaluation_tr,
                    "field": evaluation_key,
                    "value": round(evaluation_amount, 2),
                },
                "profit_loss": {
                    "tr": profit_tr,
                    "field": profit_key,
                    "value": round(profit_loss, 2),
                },
                "return_rate": {
                    "tr": return_tr,
                    "field": return_key,
                    "value": round(return_rate, 4),
                },
                "day_profit": {
                    "tr": day_profit_tr,
                    "field": day_profit_key,
                    "value": round(day_profit, 2),
                },
                "day_return_rate": {
                    "tr": day_return_tr,
                    "field": day_return_key,
                    "value": round(day_return_rate, 4),
                },
            },
        }

        return {
            "summary": {
                "total_asset": round(
                    total_asset,
                    2,
                ),
                "cash": round(
                    cash,
                    2,
                ),
                "buying_power": round(
                    buying_power,
                    2,
                ),
                "buying_power_available":
                    buying_power_available,
                "purchase_amount": round(
                    purchase_amount,
                    2,
                ),
                "evaluation_amount": round(
                    evaluation_amount,
                    2,
                ),
                "profit_loss": round(
                    profit_loss,
                    2,
                ),
                "return_rate": round(
                    return_rate,
                    4,
                ),
                "day_profit": round(
                    day_profit,
                    2,
                ),
                "day_return_rate": round(
                    day_return_rate,
                    4,
                ),
            },
            "holdings": holdings,
            "orders": orders[:100],
            "diagnostics": diagnostics,
            "account_no": account_no,
        }

    async def sync_account(
        self,
        account_no: str = "",
    ):
        probe = await self.probe_account_trs()

        return self.normalize_snapshot(
            probe,
            account_no=account_no,
        )

    async def recent_executions(self):
        """Fetch only the broker execution TR used by the global fill notifier.

        The full account snapshot touches several TRs and is intentionally rate
        limited.  A cross-page execution toast needs a lighter query, so this
        method asks only ka10076 and normalizes its order rows.
        """
        result = await self._try_variants(
            "ka10076",
            "/api/dostk/acnt",
            [
                {"qry_tp": "0", "sell_tp": "0", "stex_tp": "0"},
                {"qry_tp": "0", "sell_tp": "0", "dmst_stex_tp": "KRX"},
            ],
        )
        if not result.get("ok"):
            errors = result.get("errors") or []
            raise RuntimeError(errors[-1] if errors else "키움 체결내역을 확인하지 못했습니다.")
        payload = self.normalize_snapshot([result], account_no="")
        return [
            row for row in (payload.get("orders") or [])
            if str(row.get("source_tr") or "") == "ka10076"
            and float(row.get("filled_qty") or 0) > 0
        ]

    @staticmethod
    def _normalize_chart_date(value):
        raw = str(value or "").strip().replace("-", "")
        if len(raw) >= 8 and raw[:8].isdigit():
            raw = raw[:8]
            return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
        return ""
    
    @staticmethod
    def _chart_rows_from_response(data, index_mode=False):
        date_keys = ["dt", "date", "base_dt", "stk_dt", "trde_dt", "inds_dt"]
        open_keys = ["open_pric", "open_prc", "open_price", "open"]
        high_keys = ["high_pric", "high_prc", "high_price", "high"]
        low_keys = ["low_pric", "low_prc", "low_price", "low"]
        close_keys = ["cur_prc", "close_pric", "close_prc", "close_price", "close"]
        volume_keys = ["trde_qty", "volume", "vol", "acc_trde_qty"]
    
        found = []
        seen = set()
    
        for arr in _walk_lists(data):
            for row in arr:
                if not isinstance(row, dict):
                    continue
    
                dt = KiwoomRestClient._normalize_chart_date(
                    _first(row, date_keys, "")
                )
                if not dt:
                    continue
    
                close = abs(_num(_first(row, close_keys, 0)))
                open_ = abs(_num(_first(row, open_keys, 0)))
                high = abs(_num(_first(row, high_keys, 0)))
                low = abs(_num(_first(row, low_keys, 0)))
                volume = abs(_num(_first(row, volume_keys, 0)))
    
                if not close:
                    continue
    
                if index_mode:
                    # 키움 업종지수 값이 100배 정수형으로 오는 경우를 보정.
                    for name, value in (("close", close), ("open", open_), ("high", high), ("low", low)):
                        pass
                    if close > 10000:
                        close /= 100.0
                    if open_ > 10000:
                        open_ /= 100.0
                    if high > 10000:
                        high /= 100.0
                    if low > 10000:
                        low /= 100.0
    
                if not open_:
                    open_ = close
                if not high:
                    high = max(open_, close)
                if not low:
                    low = min(open_, close)
    
                key = dt
                if key in seen:
                    continue
                seen.add(key)
    
                found.append({
                    "date": dt,
                    "open": open_,
                    "high": high,
                    "low": low,
                    "close": close,
                    "volume": volume,
                })
    
        return sorted(found, key=lambda x: x["date"])
    
    async def _chart_request_with_variants(self, api_id, bodies, max_rows=500, index_mode=False):
        errors = []
    
        for body in bodies:
            try:
                data, headers = await self.call(
                    "/api/dostk/chart",
                    api_id,
                    body,
                )
                rows = self._chart_rows_from_response(data, index_mode=index_mode)
    
                cont_yn = headers.get("cont-yn", "")
                next_key = headers.get("next-key", "")
                pages = 1
    
                while (
                    str(cont_yn).upper() == "Y"
                    and next_key
                    and len(rows) < max_rows
                    and pages < 4
                ):
                    data2, headers2 = await self.call(
                        "/api/dostk/chart",
                        api_id,
                        body,
                        cont_yn="Y",
                        next_key=next_key,
                    )
                    rows += self._chart_rows_from_response(
                        data2,
                        index_mode=index_mode,
                    )
                    dedup = {r["date"]: r for r in rows}
                    rows = sorted(dedup.values(), key=lambda x: x["date"])
                    cont_yn = headers2.get("cont-yn", "")
                    next_key = headers2.get("next-key", "")
                    pages += 1
    
                if rows:
                    return rows[-max_rows:], {
                        "api_id": api_id,
                        "request_body": body,
                        "pages": pages,
                    }
    
                errors.append(f"{api_id}: 응답은 성공했지만 일봉 행을 찾지 못했습니다.")
            except Exception as e:
                errors.append(str(e))
    
        raise KiwoomError(" / ".join(errors[-4:]) or f"{api_id} 차트 조회 실패")
    
    @staticmethod
    def _metric_number(value):
        if value in (None, "", "-", "--"):
            return None
        try:
            raw = str(value).strip().replace(",", "").replace("%", "")
            return float(raw)
        except Exception:
            return None

    @staticmethod
    def _find_metric(data, aliases):
        alias_set = {str(x).lower() for x in aliases}

        def walk(obj):
            if isinstance(obj, dict):
                for key, value in obj.items():
                    if str(key).lower() in alias_set and value not in (None, ""):
                        return value
                for value in obj.values():
                    found = walk(value)
                    if found not in (None, ""):
                        return found
            elif isinstance(obj, list):
                for item in obj:
                    found = walk(item)
                    if found not in (None, ""):
                        return found
            return None

        return walk(data)

    async def stock_basic_metrics(self, stock_code: str):
        """Kiwoom ka10001 주식기본정보요청을 StockLog 표준 지표로 변환."""
        data, _ = await self.call(
            "/api/dostk/stkinfo",
            "ka10001",
            {"stk_cd": stock_code},
        )

        aliases = {
            "price": ("cur_prc", "cur_price", "now_pric", "price"),
            "per": ("per",),
            "pbr": ("pbr",),
            "eps": ("eps",),
            "bps": ("bps",),
            "roe": ("roe",),
            "dividend_yield": (
                "dvid_rt",
                "dvdn_rt",
                "dividend_yield",
                "div_yield",
            ),
            "market_cap": (
                "mac",
                "market_cap",
                "mrkt_tot_amt",
                "market_capitalization",
            ),
        }

        result = {"raw_api_id": "ka10001"}
        for target, keys in aliases.items():
            result[target] = self._metric_number(
                self._find_metric(data, keys)
            )

        # 절대량 계열의 부호 제거
        for key in ("price", "market_cap", "eps", "bps"):
            if result.get(key) is not None:
                result[key] = abs(result[key])

        if not any(result.get(k) is not None for k in aliases):
            top_keys = list(data.keys()) if isinstance(data, dict) else []
            raise KiwoomError(
                "ka10001 응답은 성공했지만 사용할 기본지표를 찾지 못했습니다. "
                f"top_keys={top_keys}"
            )

        return result

    async def daily_stock_chart(self, stock_code: str, max_rows: int = 500):
        from datetime import date
        today = date.today().strftime("%Y%m%d")
    
        bodies = [
            {
                "stk_cd": stock_code,
                "base_dt": today,
                "upd_stkpc_tp": "1",
            },
            {
                "stk_cd": stock_code,
                "base_dt": today,
                "upd_stkpc_tp": "0",
            },
            {
                "stk_cd": stock_code,
                "base_dt": today,
            },
        ]
        return await self._chart_request_with_variants(
            "ka10081",
            bodies,
            max_rows=max_rows,
            index_mode=False,
        )
    
    async def daily_kospi_chart(self, max_rows: int = 500):
        from datetime import date
        today = date.today().strftime("%Y%m%d")
    
        bodies = [
            {"inds_cd": "001", "base_dt": today},
            {"inds_cd": "001", "base_dt": today, "upd_stkpc_tp": "1"},
            {"inds_cd": "001"},
        ]
        return await self._chart_request_with_variants(
            "ka20006",
            bodies,
            max_rows=max_rows,
            index_mode=True,
        )

    @staticmethod
    def _normalize_stock_master_rows(data, market_name: str):
        code_keys=("code","stk_cd","stk_code","stock_code","shr_cd")
        name_keys=("name","stk_nm","stk_name","stock_name","shr_nm")

        def parse_item(obj):
            if not isinstance(obj,dict):
                return None
            code=next((str(obj[k]).strip() for k in code_keys if obj.get(k) not in (None,"")),"")
            name=next((str(obj[k]).strip() for k in name_keys if obj.get(k) not in (None,"")),"")
            if code.startswith("A") and len(code)==7:
                code=code[1:]
            if not re.fullmatch(r"\d{6}",code) or not name:
                return None
            return {"code":code,"name":name,"market":market_name}

        lists=[]
        if isinstance(data,list):
            lists=[data]
        elif isinstance(data,dict):
            for value in data.values():
                if isinstance(value,list) and value and any(parse_item(x) for x in value[:20]):
                    lists.append(value)

        rows=[]
        seen=set()
        for values in lists:
            for item in values:
                row=parse_item(item)
                if row and row["code"] not in seen:
                    seen.add(row["code"])
                    rows.append(row)
        return rows

    async def stock_info_list(self, market_type: str, market_name: str):
        all_rows=[]
        seen=set()
        cont_yn=""
        next_key=""
        page=0
        last_data={}

        while True:
            page+=1
            data,headers=await self.call(
                "/api/dostk/stkinfo",
                "ka10099",
                {"mrkt_tp":str(market_type)},
                cont_yn=cont_yn,
                next_key=next_key,
            )
            last_data=data

            for row in self._normalize_stock_master_rows(data,market_name):
                if row["code"] not in seen:
                    seen.add(row["code"])
                    all_rows.append(row)

            hcont=str(headers.get("cont-yn","")).upper()
            hnext=str(headers.get("next-key","") or "")
            if hcont!="Y" or not hnext:
                break
            cont_yn="Y"
            next_key=hnext
            if page>=50:
                raise KiwoomError("ka10099 연속조회가 50페이지를 초과했습니다.")

        if not all_rows:
            keys=list(last_data.keys()) if isinstance(last_data,dict) else []
            raise KiwoomError(f"ka10099 실제 종목목록 파싱 실패 top_keys={keys}")
        return all_rows


    async def _stock_orderbook_uncached(
        self,
        stock_code: str,
    ):
        """
        Kiwoom official domestic-stock order book.

        ka10004 /api/dostk/mrkcond
        Returns actual 10-level sell/buy quotes; no synthetic levels.
        """
        code=str(
            stock_code
            or ""
        ).strip()

        if code.startswith("A") and len(code)==7:
            code=code[1:]

        if not re.fullmatch(r"\d{6}",code):
            raise KiwoomError(
                f"올바르지 않은 종목코드입니다: {stock_code}"
            )

        data,_=await self.call(
            "/api/dostk/mrkcond",
            "ka10004",
            {
                "stk_cd":code,
            },
        )

        if not isinstance(data,dict):
            raise KiwoomError(
                "호가 응답 형식이 올바르지 않습니다."
            )

        asks=[]
        bids=[]

        for level in range(1,11):
            if level==1:
                ask_price=abs(
                    _num(
                        data.get(
                            "sel_fpr_bid"
                        )
                    )
                )
                ask_qty=abs(
                    _num(
                        data.get(
                            "sel_fpr_req"
                        )
                    )
                )
                bid_price=abs(
                    _num(
                        data.get(
                            "buy_fpr_bid"
                        )
                    )
                )
                bid_qty=abs(
                    _num(
                        data.get(
                            "buy_fpr_req"
                        )
                    )
                )
            else:
                ask_price=abs(
                    _num(
                        data.get(
                            f"sel_{level}th_pre_bid"
                        )
                    )
                )
                ask_qty=abs(
                    _num(
                        data.get(
                            f"sel_{level}th_pre_req"
                        )
                    )
                )
                bid_price=abs(
                    _num(
                        data.get(
                            f"buy_{level}th_pre_bid"
                        )
                    )
                )
                bid_qty=abs(
                    _num(
                        data.get(
                            f"buy_{level}th_pre_req"
                        )
                    )
                )

            if ask_price>0:
                asks.append(
                    {
                        "level":level,
                        "price":ask_price,
                        "quantity":ask_qty,
                    }
                )

            if bid_price>0:
                bids.append(
                    {
                        "level":level,
                        "price":bid_price,
                        "quantity":bid_qty,
                    }
                )

        # HTS display convention:
        # high sell levels at top -> best ask nearest current price at bottom.
        asks.sort(
            key=lambda x:x["level"],
            reverse=True,
        )

        bids.sort(
            key=lambda x:x["level"],
        )

        return {
            "code":code,
            "asks":asks,
            "bids":bids,
            "best_ask":(
                next(
                    (
                        item["price"]
                        for item in asks
                        if item["level"]==1
                    ),
                    None,
                )
            ),
            "best_bid":(
                next(
                    (
                        item["price"]
                        for item in bids
                        if item["level"]==1
                    ),
                    None,
                )
            ),
            "total_ask_quantity":abs(
                _num(
                    data.get(
                        "tot_sel_req"
                    )
                )
            ),
            "total_bid_quantity":abs(
                _num(
                    data.get(
                        "tot_buy_req"
                    )
                )
            ),
        }

    async def order(
        self,
        side: str,
        stock_code: str,
        quantity: int,
        order_type: str = "market",
        price: float | None = None,
        exchange: str = "KRX",
    ):
        side_value=str(side or "").lower().strip()
        if side_value not in ("buy","sell"):
            raise KiwoomError("주문 구분은 buy 또는 sell 이어야 합니다.")

        code=str(stock_code or "").strip()
        if code.startswith("A") and len(code)==7:
            code=code[1:]
        if not re.fullmatch(r"\d{6}",code):
            raise KiwoomError(f"올바르지 않은 종목코드입니다: {stock_code}")

        try:
            qty=int(quantity)
        except Exception as exc:
            raise KiwoomError("주문 수량이 올바르지 않습니다.") from exc
        if qty<=0:
            raise KiwoomError("주문 수량은 1주 이상이어야 합니다.")

        order_type_value=str(order_type or "market").lower().strip()
        if order_type_value not in ("market","limit"):
            raise KiwoomError("주문 방식은 market 또는 limit 이어야 합니다.")

        api_id="kt10000" if side_value=="buy" else "kt10001"
        trde_tp="3" if order_type_value=="market" else "0"
        body={
            "dmst_stex_tp":str(exchange or "KRX"),
            "stk_cd":code,
            "ord_qty":str(qty),
            "trde_tp":trde_tp,
        }

        if order_type_value=="limit":
            try:
                limit_price=int(float(price or 0))
            except Exception as exc:
                raise KiwoomError("지정가 주문가격이 올바르지 않습니다.") from exc
            if limit_price<=0:
                raise KiwoomError("지정가 주문은 0원보다 큰 가격이 필요합니다.")
            body["ord_uv"]=str(limit_price)

        data,_=await self.call(
            "/api/dostk/ordr",
            api_id,
            body,
        )
        return data

    async def stock_orderbook(self, stock_code: str):
        code = str(stock_code or "").strip()
        async def loader():
            return await self._stock_orderbook_uncached(code)
        value, stale = await self._cached_value(
            f"orderbook:{code}", 2.5, loader, stale_ttl=20.0
        )
        out = dict(value)
        out["stale"] = bool(stale)
        return out

    @staticmethod
    def _theme_list(data):
        if isinstance(data,list): return data
        if isinstance(data,dict):
            ls=[v for v in data.values() if isinstance(v,list)]
            return max(ls,key=len) if ls else []
        return []

    async def _collect_theme_pages(
        self,
        api_id: str,
        body: dict,
        *,
        max_pages: int = 100,
        timeout_seconds: float = 10.0,
        progress_cb=None,
    ):
        """Fetch every Kiwoom continuation page using cont-yn + next-key."""
        all_rows = []
        page_count = 0
        cont_yn = ""
        next_key = ""
        seen_next_keys = set()

        while True:
            if page_count >= max_pages:
                raise KiwoomError(
                    f"{api_id} 연속조회가 {max_pages}페이지를 초과했습니다."
                )

            request_page=page_count + 1

            if progress_cb:
                event={
                    "status":"requesting",
                    "api_id":api_id,
                    "page":request_page,
                    "message":f"{api_id} {request_page}페이지 응답 대기 중",
                }
                result=progress_cb(event)
                if asyncio.iscoroutine(result):
                    await result

            try:
                data, headers = await self.call(
                    "/api/dostk/thme",
                    api_id,
                    body,
                    cont_yn=cont_yn,
                    next_key=next_key,
                    timeout_seconds=timeout_seconds,
                    progress_cb=progress_cb,
                )
            except httpx.TimeoutException as exc:
                if progress_cb:
                    event={
                        "status":"timeout",
                        "api_id":api_id,
                        "page":request_page,
                        "message":f"{api_id} {request_page}페이지 {timeout_seconds:g}초 응답시간 초과",
                    }
                    result=progress_cb(event)
                    if asyncio.iscoroutine(result):
                        await result
                raise KiwoomError(
                    f"{api_id} page={request_page} HTTP timeout({timeout_seconds:g}s)"
                ) from exc
            except Exception as exc:
                if progress_cb:
                    event={
                        "status":"error",
                        "api_id":api_id,
                        "page":request_page,
                        "message":f"{api_id} {request_page}페이지 오류: {exc}",
                    }
                    result=progress_cb(event)
                    if asyncio.iscoroutine(result):
                        await result
                raise KiwoomError(
                    f"{api_id} 요청 실패 "
                    f"page={request_page} "
                    f"cont_yn={cont_yn!r} "
                    f"next_key={next_key!r} "
                    f"body={body}: {exc}"
                ) from exc

            page_count += 1

            if progress_cb:
                event={
                    "status":"received",
                    "api_id":api_id,
                    "page":page_count,
                    "message":f"{api_id} {page_count}페이지 수신 완료",
                }
                result=progress_cb(event)
                if asyncio.iscoroutine(result):
                    await result

            raw = self._theme_list(data)
            if raw:
                all_rows.extend(
                    item
                    for item in raw
                    if isinstance(item, dict)
                )

            response_cont = str(
                headers.get("cont-yn") or ""
            ).strip().upper()

            response_next = str(
                headers.get("next-key") or ""
            ).strip()

            if response_cont != "Y":
                break

            if not response_next:
                raise KiwoomError(
                    f"{api_id} page={page_count}: cont-yn=Y인데 next-key가 없습니다."
                )

            if response_next in seen_next_keys:
                raise KiwoomError(
                    f"{api_id} 연속조회 next-key 반복: {response_next}"
                )

            seen_next_keys.add(response_next)
            cont_yn = response_cont
            next_key = response_next

        return all_rows, page_count


    async def _theme_groups_uncached(self, progress_cb=None):
        """ka90001 전체 continuation page를 끝까지 조회합니다."""
        body = {
            "qry_tp": "0",
            "date_tp": "1",
            "thema_nm": "",
            "flu_pl_amt_tp": "1",
            "stk_cd": "",
            "stex_tp": "1",
        }

        raw, pages = await self._collect_theme_pages(
            "ka90001",
            body,
            timeout_seconds=10.0,
            progress_cb=progress_cb,
        )
        self.last_theme_group_pages = pages

        if not raw:
            raise KiwoomError(
                "ka90001 전체 연속조회 결과에 테마가 없습니다."
            )

        result_by_code = {}

        for item in raw:
            code = next(
                (
                    str(item[k]).strip()
                    for k in (
                        "thema_grp_cd",
                        "theme_grp_cd",
                        "thema_cd",
                        "theme_cd",
                        "grp_cd",
                        "code",
                    )
                    if item.get(k) not in (None, "")
                ),
                "",
            )

            name = next(
                (
                    str(item[k]).strip()
                    for k in (
                        "thema_nm",
                        "theme_nm",
                        "thema_grp_nm",
                        "theme_grp_nm",
                        "grp_nm",
                        "name",
                    )
                    if item.get(k) not in (None, "")
                ),
                "",
            )

            rate = next(
                (
                    item.get(k)
                    for k in (
                        "flu_rt",
                        "change_rate",
                        "avg_flu_rt",
                        "avg_change_rate",
                        "thema_flu_rt",
                        "flu_rt_rt",
                    )
                    if item.get(k) not in (None, "")
                ),
                None,
            )

            count = next(
                (
                    item.get(k)
                    for k in (
                        "stk_cnt",
                        "stock_cnt",
                        "cnt",
                        "item_cnt",
                    )
                    if item.get(k) not in (None, "")
                ),
                None,
            )

            if not code or not name:
                continue

            try:
                rate = (
                    float(
                        str(rate)
                        .replace(",", "")
                        .replace("+", "")
                        .replace("%", "")
                    )
                    if rate is not None
                    else None
                )
            except Exception:
                rate = None

            try:
                count = (
                    int(float(str(count).replace(",", "")))
                    if count is not None
                    else None
                )
            except Exception:
                count = None

            result_by_code[code] = {
                "theme_code": code,
                "theme_name": name,
                "change_rate": rate,
                "stock_count": count,
            }

        out = list(result_by_code.values())

        if not out:
            raise KiwoomError(
                "ka90001 전체 페이지 파싱 실패 "
                f"pages={pages} "
                f"sample_keys={list(raw[0].keys()) if raw else []}"
            )

        return out


    async def theme_groups(self, progress_cb=None):
        async def loader():
            return await self._theme_groups_uncached(progress_cb=progress_cb)
        value, stale = await self._cached_value(
            "theme_groups", 600.0, loader, stale_ttl=3600.0
        )
        self.last_theme_cache_stale = bool(stale)
        return value

    async def _theme_stocks_uncached(
        self,
        theme_code: str,
        progress_cb=None,
    ):
        """ka90002 전체 continuation page를 끝까지 조회합니다."""
        code_value = str(theme_code or "").strip()

        if not code_value:
            raise KiwoomError(
                "ka90002 테마그룹코드가 없습니다."
            )

        body = {
            "date_tp": "1",
            "thema_grp_cd": code_value,
            "stex_tp": "1",
        }

        raw, pages = await self._collect_theme_pages(
            "ka90002",
            body,
            timeout_seconds=10.0,
            progress_cb=progress_cb,
        )

        self.last_theme_stock_pages[code_value] = pages

        if progress_cb:
            event={
                "status":"parsing",
                "api_id":"ka90002",
                "page":pages,
                "message":
                    f"ka90002 응답 파싱 중 · raw {len(raw):,}행",
                "raw_count":
                    len(raw),
            }
            result=progress_cb(
                event
            )
            if asyncio.iscoroutine(
                result
            ):
                await result

        if not raw:
            return []

        result_by_code = {}

        for item in raw:
            code = next(
                (
                    str(item[k]).strip()
                    for k in (
                        "stk_cd",
                        "stock_code",
                        "code",
                        "jongmok_cd",
                    )
                    if item.get(k) not in (None, "")
                ),
                "",
            )

            if code.startswith("A") and len(code) == 7:
                code = code[1:]

            if not re.fullmatch(r"\d{6}", code):
                continue

            name = next(
                (
                    str(item[k]).strip()
                    for k in (
                        "stk_nm",
                        "stock_name",
                        "name",
                        "jongmok_nm",
                    )
                    if item.get(k) not in (None, "")
                ),
                "",
            )

            rate = next(
                (
                    item.get(k)
                    for k in (
                        "flu_rt",
                        "change_rate",
                        "flu_rt_rt",
                    )
                    if item.get(k) not in (None, "")
                ),
                None,
            )

            price = next(
                (
                    item.get(k)
                    for k in (
                        "cur_prc",
                        "price",
                        "now_prc",
                    )
                    if item.get(k) not in (None, "")
                ),
                None,
            )

            try:
                rate = (
                    float(
                        str(rate)
                        .replace(",", "")
                        .replace("+", "")
                        .replace("%", "")
                    )
                    if rate is not None
                    else None
                )
            except Exception:
                rate = None

            try:
                price = (
                    abs(float(str(price).replace(",", "").replace("+", "")))
                    if price is not None
                    else None
                )
            except Exception:
                price = None

            result_by_code[code] = {
                "code": code,
                "name": name,
                "change_rate": rate,
                "price": price,
            }

        out = list(result_by_code.values())

        if progress_cb:
            event={
                "status":"parsed",
                "api_id":"ka90002",
                "page":pages,
                "message":
                    f"ka90002 파싱 완료 · 종목 {len(out):,}개",
                "raw_count":
                    len(raw),
                "member_count":
                    len(out),
            }
            result=progress_cb(
                event
            )
            if asyncio.iscoroutine(
                result
            ):
                await result

        if raw and not out:
            raise KiwoomError(
                "ka90002 전체 페이지 파싱 실패 "
                f"theme_code={code_value} "
                f"pages={pages} "
                f"sample_keys={list(raw[0].keys())}"
            )

        return out

    async def theme_stocks(self, theme_code: str, progress_cb=None):
        code_value = str(theme_code or "").strip()
        async def loader():
            return await self._theme_stocks_uncached(code_value, progress_cb=progress_cb)
        value, stale = await self._cached_value(
            f"theme_stocks:{code_value}", 600.0, loader, stale_ttl=3600.0
        )
        return value
