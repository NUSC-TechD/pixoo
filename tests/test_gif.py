from io import BytesIO

from PIL import GifImagePlugin, Image

from pixoo_server.display.gif import encode_gif
from pixoo_server.display.models import FrameSequence


def test_preserves_repeated_static_frames_and_short_delays() -> None:
    frame = bytes((40, 100, 200)) * (64 * 64)
    sequence = FrameSequence(frames=[frame] * 20, speed_ms=250)

    with Image.open(BytesIO(encode_gif(sequence))) as animation:
        assert animation.n_frames == 20
        assert animation.info["loop"] == 0
        for index in range(animation.n_frames):
            animation.seek(index)
            assert animation.info["duration"] == 250
            assert animation.convert("RGB").tobytes() == frame


def test_writes_complete_frames_with_a_shared_palette(monkeypatch) -> None:
    # Keep decoded frames indexed unless the file introduces another palette.
    monkeypatch.setattr(
        GifImagePlugin,
        "LOADING_STRATEGY",
        GifImagePlugin.LoadingStrategy.RGB_AFTER_DIFFERENT_PALETTE_ONLY,
    )
    first = bytes((4, 8, 14)) * (64 * 64)
    second = bytearray(first)
    second[(32 * 64 + 32) * 3 : (32 * 64 + 32) * 3 + 3] = bytes((250, 100, 30))
    frames = [first, bytes(second), first]

    with Image.open(BytesIO(encode_gif(FrameSequence(frames=frames)))) as animation:
        palette = None
        for index, expected in enumerate(frames):
            animation.seek(index)
            assert animation.tile[0][1] == (0, 0, 64, 64)
            assert animation.disposal_method == 1
            assert "transparency" not in animation.info
            if palette is None:
                palette = animation.getpalette()
                assert palette is not None
            assert animation.getpalette() == palette
            assert animation.convert("RGB").tobytes() == expected
