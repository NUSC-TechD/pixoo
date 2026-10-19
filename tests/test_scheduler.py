import asyncio
from io import BytesIO

import httpx
import pytest
from PIL import Image

from pixoo_server.config.models import PixooConfig, ViewConfig
from pixoo_server.display.gif import encode_gif
from pixoo_server.display.models import FrameSequence
from pixoo_server.display.scheduler import DisplayScheduler, build_playlist
from pixoo_server.display.screens.bus_arrival import (
    BusArrivalScreen,
    BusStopTimings,
    BusTiming,
    render_frame,
    render_unavailable,
)
from pixoo_server.display.screens.haze import PSI_URL, WEATHER_URL, HazeScreen
from pixoo_server.display.screens.haze import render_frame as render_haze_frame
from pixoo_server.display.screens.unavailable import render_unavailable as render_unavailable_notice


def test_playlist_repeats_each_view_for_its_duration() -> None:
    frame_a = bytes(64 * 64 * 3)
    frame_b = bytes([1]) * (64 * 64 * 3)
    sequence = FrameSequence(frames=[frame_a, frame_b], speed_ms=250)
    view = ViewConfig(type="haze", duration_seconds=2)

    playlist = build_playlist([(view, sequence)])

    assert playlist.speed_ms == 250
    assert len(playlist.frames) == 8
    assert playlist.frames[:2] == [frame_a, frame_b]

    animation = Image.open(BytesIO(encode_gif(playlist)))
    assert animation.size == (64, 64)
    assert animation.n_frames == 8
    assert animation.info["duration"] == 250
    assert animation.info["loop"] == 0


def test_playlist_shows_each_content_screen_for_ten_seconds_by_default() -> None:
    frame_a = bytes(64 * 64 * 3)
    frame_b = bytes([1]) * (64 * 64 * 3)
    first = FrameSequence(frames=[frame_a], speed_ms=1000)
    second = FrameSequence(frames=[frame_b], speed_ms=1000)

    playlist = build_playlist(
        [
            (ViewConfig(type="haze"), first),
            (ViewConfig(type="haze"), second),
        ]
    )

    assert playlist.frames == [frame_a] * 10 + [frame_b] * 10


def test_bus_frame_can_share_a_playlist_with_an_animated_screen() -> None:
    animated = FrameSequence(frames=[bytes(64 * 64 * 3)] * 8, speed_ms=250)
    arrivals = BusStopTimings(
        busStopName="UTOWN",
        busStopCaption="University Town",
        timings=[BusTiming(name="D1", arrivalTime="10", nextArrivalTime="35")],
    )
    bus = FrameSequence(frames=[render_frame(arrivals)], speed_ms=250)

    playlist = build_playlist(
        [
            (ViewConfig(type="haze"), animated),
            (ViewConfig(type="bus_arrival"), bus),
        ]
    )

    assert playlist.speed_ms == 250
    assert len(playlist.frames) == 80


def test_encoded_haze_and_bus_each_last_exactly_five_seconds() -> None:
    haze = FrameSequence(
        frames=[
            render_haze_frame(
                171,
                {"forecast": "Partly Cloudy", "low": 25, "high": 32, "date": "2026-10-18"},
                phase,
            )
            for phase in range(8)
        ]
    )
    bus_frame = render_frame(
        BusStopTimings(
            busStopName="UTOWN",
            busStopCaption="University Town",
            timings=[BusTiming(name="D1", arrivalTime="10", nextArrivalTime="35")],
        )
    )
    playlist = build_playlist(
        [
            (ViewConfig(type="haze", duration_seconds=5), haze),
            (ViewConfig(type="bus_arrival", duration_seconds=5), FrameSequence(frames=[bus_frame])),
        ]
    )

    assert playlist.frames == (haze.frames * 3)[:20] + [bus_frame] * 20
    with Image.open(BytesIO(encode_gif(playlist))) as animation:
        assert animation.n_frames == 40
        durations = []
        for index in range(animation.n_frames):
            animation.seek(index)
            assert animation.tile[0][1] == (0, 0, 64, 64)
            durations.append(animation.info["duration"])
            assert animation.convert("RGB").tobytes() == playlist.frames[index]
        assert durations == [250] * 40
        assert sum(durations[:20]) == 5000
        assert sum(durations[20:]) == 5000


def test_bus_failure_keeps_haze_refreshing_and_uploads_fallback(monkeypatch) -> None:
    haze_renders = 0

    async def render_haze(self, client, options) -> FrameSequence:
        nonlocal haze_renders
        haze_renders += 1
        return FrameSequence(frames=[bytes((haze_renders, 8, 14)) * (64 * 64)])

    monkeypatch.setattr(HazeScreen, "render", render_haze)

    async def run() -> None:
        uploads = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal uploads
            if request.method == "POST":
                uploads += 1
                return httpx.Response(200, json={"error_code": 0})
            return httpx.Response(503)

        config = PixooConfig(
            name="test",
            address="pixoo.example",
            views=[
                ViewConfig(type="haze", duration_seconds=5),
                ViewConfig(type="bus_arrival", duration_seconds=5),
            ],
        )
        scheduler = DisplayScheduler(
            (config,), None, "http://server.example", "https://bus.example/api/stop"
        )
        fallback = render_unavailable("UTOWN")
        now = 0.0
        scheduler._screen_types["bus_arrival"] = BusArrivalScreen(
            "https://bus.example/api/stop", clock=lambda: now
        )
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            scheduler._client = client
            for attempt in (1, 2):
                now = attempt * 120.0
                await scheduler.refresh("test")
                data = scheduler.animation("test")
                assert data is not None
                with Image.open(BytesIO(data)) as animation:
                    assert animation.n_frames == 40
                    assert animation.convert("RGB").tobytes() == (
                        bytes((attempt, 8, 14)) * (64 * 64)
                    )
                    for index in range(20):
                        animation.seek(20 + index)
                        assert animation.info["duration"] == 250
                        assert animation.convert("RGB").tobytes() == fallback.frames[index % 8]
                assert scheduler.statuses["test"].last_error is None
                assert scheduler.statuses["test"].last_updated_at is not None
        assert uploads == 2

    asyncio.run(run())
    assert haze_renders == 2


@pytest.mark.parametrize("failed_url", [PSI_URL, WEATHER_URL])
def test_haze_failure_keeps_bus_timings_refreshing(failed_url: str) -> None:
    async def run() -> None:
        bus_requests = 0
        uploads = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal bus_requests, uploads
            if request.method == "POST":
                uploads += 1
                return httpx.Response(200, json={"error_code": 0})
            if request.url.host == "bus.example":
                bus_requests += 1
                return httpx.Response(
                    200,
                    json={
                        "etas": {
                            "busStopName": "UTOWN",
                            "busStopCaption": "University Town",
                            "timings": [
                                {
                                    "name": "D1",
                                    "arrivalTime": str(11 - bus_requests),
                                    "nextArrivalTime": "35",
                                }
                            ],
                        }
                    },
                )
            if str(request.url) == failed_url:
                return httpx.Response(503)
            return httpx.Response(200, json={})

        config = PixooConfig(
            name="test",
            address="pixoo.example",
            views=[
                ViewConfig(type="haze", duration_seconds=5),
                ViewConfig(type="bus_arrival", duration_seconds=5),
            ],
        )
        scheduler = DisplayScheduler(
            (config,), None, "http://server.example", "https://bus.example/api/stop"
        )
        fallback = render_unavailable_notice("HAZE")
        now = 0.0
        scheduler._screen_types["bus_arrival"] = BusArrivalScreen(
            "https://bus.example/api/stop", clock=lambda: now
        )
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            scheduler._client = client
            for attempt in (1, 2):
                now = attempt * 120.0
                await scheduler.refresh("test")
                data = scheduler.animation("test")
                assert data is not None
                with Image.open(BytesIO(data)) as animation:
                    assert animation.n_frames == 40
                    for index in range(20):
                        animation.seek(index)
                        assert animation.convert("RGB").tobytes() == fallback.frames[index % 8]
                    animation.seek(20)
                    expected = render_frame(
                        BusStopTimings(
                            busStopName="UTOWN",
                            busStopCaption="University Town",
                            timings=[
                                BusTiming(
                                    name="D1", arrivalTime=str(11 - attempt), nextArrivalTime="35"
                                )
                            ],
                        )
                    )
                    assert animation.convert("RGB").tobytes() == expected
                assert scheduler.statuses["test"].last_error is None
        assert bus_requests == 2
        assert uploads == 2

    asyncio.run(run())
