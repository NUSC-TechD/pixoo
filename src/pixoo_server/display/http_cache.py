"""Rate-limited, cached JSON fetching for third-party APIs."""

from __future__ import annotations

import asyncio
import logging
import random
import re
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

logger = logging.getLogger(__name__)

MAX_AGE_PATTERN = re.compile(r"(?:^|[,\s])max-age\s*=\s*\"?(\d+)", re.IGNORECASE)


class FetchThrottledError(RuntimeError):
    """Signal that a request was suppressed by the rate limit or error backoff."""


@dataclass
class _Entry:
    payload: Any = None
    etag: str | None = None
    last_modified: str | None = None
    fresh_until: float = float("-inf")
    next_request_at: float = float("-inf")
    failures: int = 0
    has_payload: bool = False


class CachedJsonFetcher:
    """Fetch JSON with a per-URL hard rate limit, response caching, and backoff.

    Every URL is requested at most once per ``min_interval`` seconds, no matter
    how many callers ask for it; concurrent callers share one in-flight request.
    Successful responses are cached for ``min_interval`` or the server's
    ``Cache-Control: max-age``, whichever is longer, and are revalidated with
    ``ETag``/``Last-Modified`` when the server provides them. Failures back off
    exponentially with jitter (honouring ``Retry-After``) up to ``max_backoff``.
    """

    def __init__(
        self,
        headers: Mapping[str, str],
        *,
        min_interval: float = 60,
        max_backoff: float = 30 * 60,
        clock: Callable[[], float] = time.monotonic,
        jitter: Callable[[float, float], float] = random.uniform,
    ) -> None:
        self._headers = dict(headers)
        self._min_interval = min_interval
        self._max_backoff = max_backoff
        self._clock = clock
        self._jitter = jitter
        self._entries: dict[str, _Entry] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    async def get_json(self, client: httpx.AsyncClient, url: str) -> Any:
        lock = self._locks.setdefault(url, asyncio.Lock())
        async with lock:
            entry = self._entries.setdefault(url, _Entry())
            now = self._clock()
            if entry.has_payload and now < entry.fresh_until:
                return entry.payload
            if now < entry.next_request_at:
                raise FetchThrottledError(
                    f"{url} not requested; next request allowed in "
                    f"{entry.next_request_at - now:.0f}s"
                )
            entry.next_request_at = now + self._min_interval
            try:
                response = await client.get(url, headers=self._request_headers(entry))
                return self._store(entry, response)
            except (httpx.HTTPError, ValueError) as error:
                self._back_off(entry, now, error)
                raise

    def _request_headers(self, entry: _Entry) -> dict[str, str]:
        headers = dict(self._headers)
        if entry.has_payload and entry.etag:
            headers["If-None-Match"] = entry.etag
        if entry.has_payload and entry.last_modified:
            headers["If-Modified-Since"] = entry.last_modified
        return headers

    def _store(self, entry: _Entry, response: httpx.Response) -> Any:
        now = self._clock()
        if response.status_code == 304 and entry.has_payload:
            payload = entry.payload
        else:
            response.raise_for_status()
            payload = response.json()
        entry.payload = payload
        entry.has_payload = True
        entry.etag = response.headers.get("etag", entry.etag)
        entry.last_modified = response.headers.get("last-modified", entry.last_modified)
        entry.fresh_until = now + max(self._min_interval, _max_age(response))
        entry.failures = 0
        return payload

    def _back_off(self, entry: _Entry, now: float, error: Exception) -> None:
        entry.failures += 1
        ceiling = min(self._max_backoff, self._min_interval * 2 ** (entry.failures - 1))
        delay = max(self._min_interval, self._jitter(ceiling / 2, ceiling))
        if isinstance(error, httpx.HTTPStatusError):
            delay = max(delay, min(self._max_backoff, _retry_after(error.response)))
        entry.next_request_at = now + delay
        logger.warning(
            "Request failed (%d in a row); backing off %.0fs: %s", entry.failures, delay, error
        )


def _max_age(response: httpx.Response) -> float:
    match = MAX_AGE_PATTERN.search(response.headers.get("cache-control", ""))
    return float(match.group(1)) if match else 0


def _retry_after(response: httpx.Response) -> float:
    value = response.headers.get("retry-after", "").strip()
    if value.isdigit():
        return float(value)
    try:
        return max(0.0, parsedate_to_datetime(value).timestamp() - time.time())
    except (TypeError, ValueError):
        return 0
