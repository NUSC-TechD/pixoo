from io import BytesIO

from PIL import Image

from pixoo_server.config.models import ViewConfig
from pixoo_server.display.gif import encode_gif
from pixoo_server.display.models import FrameSequence
from pixoo_server.display.scheduler import build_playlist
from pixoo_server.display.screens.bus_arrival import BusStopTimings, BusTiming, render_frame
from pixoo_server.display.screens.haze import render_frame as render_haze_frame


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
