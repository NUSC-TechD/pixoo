from __future__ import annotations

import asyncio
import logging
import math
from datetime import UTC, datetime

import httpx
from pydantic import BaseModel, ConfigDict

from pixoo_server.config.models import PixooConfig, ViewConfig

from .client import PixooClient
from .gif import encode_gif
from .models import FrameSequence
from .screens.bus_arrival import BusArrivalScreen
from .screens.haze import HazeScreen

logger = logging.getLogger(__name__)


class ScreenStatus(BaseModel):
    """Record mutable scheduler state for one configured screen.

    It reports whether an update is running and the outcome of the most recent
    attempt. Operational state lives here instead of in the validated,
    effectively static :class:`PixooConfig`.
    """

    model_config = ConfigDict(validate_assignment=True)

    name: str
    updating: bool = False
    last_updated_at: str | None = None
    last_error: str | None = None


class DisplayScheduler:
    """Render and refresh playlists for all configured physical screens.

    The scheduler runs one periodic task per :class:`PixooConfig`, delegates
    each view to its content screen, combines the sequences into a hosted
    GIF, and tells the screen to download it through :class:`PixooClient`. It
    also exposes the latest update status and retries failures on the next cycle.
    """

    def __init__(
        self,
        screens: tuple[PixooConfig, ...],
        api_key: str | None,
        media_base_url: str,
        bus_api_base_url: str = "https://bus.hewliyang.com/api/stop",
    ) -> None:
        self.screens = {screen.name: screen for screen in screens}
        self.statuses = {name: ScreenStatus(name=name) for name in self.screens}
        self._animations: dict[str, bytes] = {}
        self._media_base_url = media_base_url.rstrip("/")
        self._screen_types = {
            "haze": HazeScreen(api_key),
            "bus_arrival": BusArrivalScreen(bus_api_base_url),
        }
        self._tasks: list[asyncio.Task[None]] = []
        self._client: httpx.AsyncClient | None = None

    async def start(self) -> None:
        self._client = httpx.AsyncClient(timeout=15)
        self._tasks = [
            asyncio.create_task(self._run(screen), name=f"screen:{screen.name}")
            for screen in self.screens.values()
        ]

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        if self._client:
            await self._client.aclose()

    async def refresh(self, name: str) -> None:
        if name not in self.screens:
            raise KeyError(name)
        if not self._client:
            raise RuntimeError("Display scheduler is not running")
        status = self.statuses[name]
        if status.updating:
            raise RuntimeError(f"Screen {name} is already updating")
        status.updating = True
        try:
            screen = self.screens[name]
            sequences = [await self._render(view) for view in screen.views]
            playlist = build_playlist(list(zip(screen.views, sequences, strict=True)))
            self._animations[name] = encode_gif(playlist)
            gif_url = f"{self._media_base_url}/api/screens/{name}/animation.gif"
            await PixooClient(self._client).play_gif_url(screen.address, gif_url)
            status.last_updated_at = datetime.now(UTC).isoformat()
            status.last_error = None
        except Exception as error:
            status.last_error = str(error)
            raise
        finally:
            status.updating = False

    def snapshot(self) -> list[dict[str, object]]:
        return [
            {
                **self.statuses[name].model_dump(),
                "address": screen.address,
                "refresh_seconds": screen.refresh_seconds,
                "views": [view.type for view in screen.views],
            }
            for name, screen in self.screens.items()
        ]

    def animation(self, name: str) -> bytes | None:
        """Return the latest encoded GIF for a screen, if it has rendered."""
        return self._animations.get(name)

    async def _render(self, view: ViewConfig) -> FrameSequence:
        if not self._client:
            raise RuntimeError("Display scheduler is not running")
        return await self._screen_types[view.type].render(self._client, view.options)

    async def _run(self, screen: PixooConfig) -> None:
        while True:
            try:
                await self.refresh(screen.name)
                delay = screen.refresh_seconds
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Screen update failed: %s", screen.name)
                delay = 60
            await asyncio.sleep(delay)


def build_playlist(items: list[tuple[ViewConfig, FrameSequence]]) -> FrameSequence:
    if not items:
        raise ValueError("A playlist needs at least one view")
    speed_ms = items[0][1].speed_ms
    if any(sequence.speed_ms != speed_ms for _, sequence in items):
        raise ValueError("All views in a playlist must use the same frame speed")
    frames: list[bytes] = []
    for view, sequence in items:
        sequence_duration_ms = len(sequence.frames) * speed_ms
        repeats = max(1, math.ceil(view.duration_seconds * 1000 / sequence_duration_ms))
        frames.extend(sequence.frames * repeats)
    return FrameSequence(frames=frames, speed_ms=speed_ms)
