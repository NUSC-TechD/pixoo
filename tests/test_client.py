import asyncio
import json

import httpx
import pytest

from pixoo_server.display.client import PixooClient


def test_tells_pixoo_to_download_hosted_gif() -> None:
    requests: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={"error_code": 0})

    async def scenario() -> None:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            await PixooClient(client).play_gif_url(
                "10.42.0.8",
                "http://10.42.0.1/api/screens/makerspace/animation.gif",
            )

    asyncio.run(scenario())

    assert requests == [
        {
            "Command": "Device/PlayTFGif",
            "FileType": 2,
            "FileName": "http://10.42.0.1/api/screens/makerspace/animation.gif",
        }
    ]


def test_retries_timeouts_with_exponential_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts = 0
    delays: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 8:
            raise httpx.ReadTimeout("Pixoo timed out", request=request)
        return httpx.Response(200, json={"error_code": 0})

    async def fake_sleep(delay: float) -> None:
        delays.append(delay)

    async def scenario() -> None:
        monkeypatch.setattr(asyncio, "sleep", fake_sleep)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await PixooClient(client).play_gif_url("10.42.0.8", "http://server/animation.gif")

    asyncio.run(scenario())

    assert attempts == 8
    assert delays == [0.5, 1, 2, 4, 8, 8, 8]


def test_does_not_retry_board_rejection(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts = 0
    delays: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(200, json={"error_code": 2})

    async def fake_sleep(delay: float) -> None:
        delays.append(delay)

    async def scenario() -> None:
        monkeypatch.setattr(asyncio, "sleep", fake_sleep)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(RuntimeError, match="Pixoo rejected the request"):
                await PixooClient(client).play_gif_url(
                    "10.42.0.8", "http://server/animation.gif"
                )

    asyncio.run(scenario())

    assert attempts == 1
    assert delays == []
