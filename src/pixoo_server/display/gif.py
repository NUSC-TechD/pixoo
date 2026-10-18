"""Encode rendered Pixoo frames as GIF files."""

from io import BytesIO

from PIL import Image

from .models import FrameSequence


def encode_gif(sequence: FrameSequence) -> bytes:
    """Encode a frame sequence as a looping 64-by-64 GIF."""
    images = [Image.frombytes("RGB", (64, 64), frame) for frame in sequence.frames]
    output = BytesIO()
    images[0].save(
        output,
        format="GIF",
        save_all=True,
        append_images=images[1:],
        duration=sequence.speed_ms,
        loop=0,
        optimize=False,
    )
    return output.getvalue()
