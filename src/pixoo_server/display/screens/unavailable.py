"""Shared unavailable-data animation for information screens."""

from ..drawing import draw_centered, draw_text, fill_rect, new_frame, text_width
from ..models import FrameSequence


def render_unavailable(title: str) -> FrameSequence:
    """Show an unavailable-data notice with dots advancing every half second."""
    frame = new_frame()
    draw_centered(frame, title[:16], 2, (235, 240, 245))
    fill_rect(frame, 2, 9, 60, 1, (35, 45, 55))
    draw_centered(frame, "LIVE DATA", 23, (235, 240, 245))
    draw_centered(frame, "UNAVAILABLE", 32, (245, 170, 65))
    # Reserve all three dots so the word stays in place as the dots animate.
    x = (64 - text_width("RETRYING...")) // 2
    draw_text(frame, "RETRYING", x, 48, (135, 145, 155))
    frames = []
    for dots in range(4):
        phase = frame.copy()
        draw_text(phase, "." * dots, x + 8 * 4, 48, (135, 145, 155))
        frames.extend([bytes(phase)] * 2)
    return FrameSequence(frames=frames, speed_ms=250)
