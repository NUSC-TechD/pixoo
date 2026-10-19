import asyncio

import httpx
import pytest

from pixoo_server.display.http_cache import CachedJsonFetcher, FetchThrottledError

URL = "https://api.example/resource"


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def fetcher(clock: Clock, **kwargs) -> CachedJsonFetcher:
    return CachedJsonFetcher(
        {"User-Agent": "test-bot/1.0"},
        clock=clock,
        jitter=lambda low, high: high,
        **kwargs,
    )


def test_repeated_and_concurrent_calls_share_one_request_per_minute() -> None:
    async def run() -> None:
        calls = 0

        async def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            await asyncio.sleep(0)
            assert request.headers["user-agent"] == "test-bot/1.0"
            return httpx.Response(200, json={"n": calls})

        clock = Clock()
        cache = fetcher(clock)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            results = await asyncio.gather(*(cache.get_json(client, URL) for _ in range(500)))
            assert results == [{"n": 1}] * 500
            clock.now = 59.9
            assert await cache.get_json(client, URL) == {"n": 1}
            clock.now = 60
            assert await cache.get_json(client, URL) == {"n": 2}
        assert calls == 2

    asyncio.run(run())


def test_respects_longer_max_age_and_revalidates_with_etag() -> None:
    async def run() -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if request.headers.get("if-none-match") == '"v1"':
                return httpx.Response(304, headers={"Cache-Control": "max-age=300"})
            return httpx.Response(
                200,
                json={"v": 1},
                headers={"ETag": '"v1"', "Cache-Control": "public, max-age=300"},
            )

        clock = Clock()
        cache = fetcher(clock)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            assert await cache.get_json(client, URL) == {"v": 1}
            clock.now = 299
            assert await cache.get_json(client, URL) == {"v": 1}
            assert len(requests) == 1
            clock.now = 300
            assert await cache.get_json(client, URL) == {"v": 1}
        assert len(requests) == 2
        assert requests[1].headers["if-none-match"] == '"v1"'

    asyncio.run(run())


def test_no_cache_header_does_not_bypass_minimum_interval() -> None:
    async def run() -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(200, json={}, headers={"Cache-Control": "no-store"})

        clock = Clock()
        cache = fetcher(clock)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            for second in range(60):
                clock.now = second
                await cache.get_json(client, URL)
        assert calls == 1

    asyncio.run(run())


def test_failures_back_off_exponentially_and_honour_retry_after() -> None:
    async def run() -> None:
        attempts: list[float] = []
        retry_after = None

        def handler(request: httpx.Request) -> httpx.Response:
            attempts.append(clock.now)
            headers = {"Retry-After": retry_after} if retry_after else {}
            return httpx.Response(503, headers=headers)

        clock = Clock()
        cache = fetcher(clock, max_backoff=480)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            for second in range(0, 1500):
                clock.now = second
                with pytest.raises((httpx.HTTPStatusError, FetchThrottledError)):
                    await cache.get_json(client, URL)
            # Backoff doubles from one minute and caps at eight minutes.
            assert attempts == [0, 60, 180, 420, 900, 1380]

            retry_after = "1200"
            clock.now = 1860
            with pytest.raises(httpx.HTTPStatusError):
                await cache.get_json(client, URL)
            clock.now = 1860 + 479
            with pytest.raises(FetchThrottledError):
                await cache.get_json(client, URL)

    asyncio.run(run())


def test_success_after_failure_resets_backoff() -> None:
    async def run() -> None:
        fail = True

        def handler(request: httpx.Request) -> httpx.Response:
            if fail:
                raise httpx.ConnectError("down", request=request)
            return httpx.Response(200, json={"ok": True})

        clock = Clock()
        cache = fetcher(clock)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            for now in (0, 60, 180):
                clock.now = now
                with pytest.raises(httpx.ConnectError):
                    await cache.get_json(client, URL)
            fail = False
            clock.now = 420
            assert await cache.get_json(client, URL) == {"ok": True}
            fail = True
            clock.now = 480
            with pytest.raises(httpx.ConnectError):
                await cache.get_json(client, URL)
            clock.now = 540
            with pytest.raises(httpx.ConnectError):
                await cache.get_json(client, URL)

    asyncio.run(run())
