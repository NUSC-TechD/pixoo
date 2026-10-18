"""HTTP client for directing a physical Pixoo to hosted content."""

from __future__ import annotations

import asyncio

import httpx


class PixooClient:
    """Tell one physical Pixoo to download and play a hosted GIF.

    The client sends the Pixoo local API's network-GIF command, validates the
    response, and retries transient failures. It does not create or host the
    GIF and it keeps synchronous community-library calls out of the event loop.
    """

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def play_gif_url(self, address: str, gif_url: str) -> None:
        await self._post(
            address,
            {
                "Command": "Device/PlayTFGif",
                "FileType": 2,
                "FileName": gif_url,
            },
        )

    async def _post(self, address: str, payload: dict[str, object]) -> None:
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                response = await self._client.post(f"http://{address}/post", json=payload)
                response.raise_for_status()
                result = response.json()
                if result.get("error_code", result.get("errorCode", 0)) != 0:
                    raise RuntimeError(f"Pixoo rejected the request: {result}")
                return
            except (httpx.HTTPError, ValueError, RuntimeError) as error:
                last_error = error
                if attempt < 2:
                    await asyncio.sleep(2)
        raise RuntimeError(f"Pixoo at {address} is unreachable: {last_error}") from last_error
