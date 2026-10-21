"""HTTP client for directing a physical Pixoo to hosted content."""

from __future__ import annotations

import asyncio

import httpx
from tenacity import (
    AsyncRetrying,
    retry_if_exception,
    stop_after_attempt,
    stop_before_delay,
    wait_exponential,
)

BOARD_REQUEST_TIMEOUT_SECONDS = 5
BOARD_RETRY_WINDOW_SECONDS = 60
BOARD_MAX_ATTEMPTS = 8


def _is_retryable(error: BaseException) -> bool:
    """Return whether another attempt could recover from the failure."""
    if isinstance(error, (httpx.TransportError, ValueError)):
        return True
    return isinstance(error, httpx.HTTPStatusError) and error.response.status_code >= 500


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
        try:
            async for attempt in AsyncRetrying(
                stop=(
                    stop_after_attempt(BOARD_MAX_ATTEMPTS)
                    | stop_before_delay(BOARD_RETRY_WINDOW_SECONDS)
                ),
                wait=wait_exponential(multiplier=0.5, min=0.5, max=8),
                retry=retry_if_exception(_is_retryable),
                sleep=asyncio.sleep,
                reraise=True,
            ):
                with attempt:
                    response = await self._client.post(
                        f"http://{address}/post",
                        json=payload,
                        timeout=BOARD_REQUEST_TIMEOUT_SECONDS,
                    )
                    response.raise_for_status()
                    result = response.json()
                    if result.get("error_code", result.get("errorCode", 0)) != 0:
                        raise RuntimeError(f"Pixoo rejected the request: {result}")
                    return
        except (httpx.HTTPError, ValueError) as error:
            raise RuntimeError(f"Pixoo at {address} is unreachable: {error}") from error
