import asyncio
import time

from backend.app.kiwoom import KiwoomRestClient


def test_cancelled_gate_waiter_is_removed():
    async def scenario():
        client=KiwoomRestClient("app","secret")
        client.GATE_WAIT_TIMEOUT_SECONDS=1.0
        await client._acquire_gate("owner")
        waiter=asyncio.create_task(client._acquire_gate("waiter"))
        await asyncio.sleep(0.02)
        waiter.cancel()
        try:
            await waiter
        except asyncio.CancelledError:
            pass
        assert client._gate_queue == []
        await client._release_gate()
        await asyncio.wait_for(client._acquire_gate("next"),0.2)
        await client._release_gate()
    asyncio.run(scenario())


def test_cancel_during_throttle_releases_active_gate():
    async def scenario():
        client=KiwoomRestClient("app","secret")
        client.token="test-token"
        client._token_valid_until_monotonic=time.monotonic()+60.0
        client.GLOBAL_MIN_INTERVAL=10.0
        client._global_last_request=time.monotonic()
        task=asyncio.create_task(
            client._post_once(path="/never-sent",api_id="slow",body={},timeout_seconds=0.1)
        )
        await asyncio.sleep(0.03)
        assert client._gate_active is True
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        assert client._gate_active is False
        assert client._gate_active_api_id == ""
        await asyncio.wait_for(client._acquire_gate("next"),0.2)
        await client._release_gate()
    asyncio.run(scenario())
