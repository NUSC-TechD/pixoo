"""Encode rendered Pixoo frames as GIF files."""

from io import BytesIO

from PIL import GifImagePlugin, Image

from .models import FrameSequence


def encode_gif(sequence: FrameSequence) -> bytes:
    """Encode full frames with one palette and a constant playback delay.

    Pillow's multi-frame save merges identical frames and crops updates, even
    with optimization disabled. Write each frame separately so the Pixoo does
    not need long frame delays, partial-frame compositing, or palette changes.
    """
    unique_frames = list(dict.fromkeys(sequence.frames))
    palette = Image.frombytes("RGB", (64, 64 * len(unique_frames)), b"".join(unique_frames))
    palette = palette.quantize(colors=256, dither=Image.Dither.NONE)
    images = {
        frame: Image.frombytes("RGB", (64, 64), frame).quantize(
            palette=palette, dither=Image.Dither.NONE
        )
        for frame in unique_frames
    }
    output = BytesIO()
    header, _ = GifImagePlugin.getheader(
        images[sequence.frames[0]], info={"loop": 0, "optimize": False}
    )
    for block in header:
        output.write(block)
    for frame in sequence.frames:
        for block in GifImagePlugin.getdata(images[frame], duration=sequence.speed_ms, disposal=1):
            output.write(block)
    output.write(b";")
    return output.getvalue()
