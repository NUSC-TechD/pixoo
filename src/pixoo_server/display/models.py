from pydantic import BaseModel, ConfigDict, field_validator


class FrameSequence(BaseModel):
    """Hold a validated Pixoo animation that is ready for GIF encoding.

    Each frame contains raw RGB bytes for a 64-by-64 display, and ``speed_ms``
    controls the duration of every frame. Renderers create sequences, the
    scheduler combines them, and the GIF encoder turns the result into a file
    that the Pixoo can download.
    """

    model_config = ConfigDict(frozen=True)

    frames: list[bytes]
    speed_ms: int = 250

    @field_validator("frames")
    @classmethod
    def validate_frames(cls, frames: list[bytes]) -> list[bytes]:
        expected_size = 64 * 64 * 3
        if not frames or any(len(frame) != expected_size for frame in frames):
            raise ValueError("Every sequence needs at least one 64x64 RGB frame")
        return frames
