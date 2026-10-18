import pytest
from pydantic import BaseModel, ValidationError

from pixoo_server.cloud_emulator.state import DeviceStatus
from pixoo_server.display.models import FrameSequence
from pixoo_server.display.scheduler import ScreenStatus
from pixoo_server.mqtt.protocol import ConnectInfo


@pytest.mark.parametrize(
    "model",
    [DeviceStatus, FrameSequence, ScreenStatus, ConnectInfo],
)
def test_runtime_data_models_use_pydantic(model: type[BaseModel]) -> None:
    assert issubclass(model, BaseModel)


def test_frame_sequence_validates_frame_dimensions() -> None:
    with pytest.raises(ValidationError, match="at least one 64x64 RGB frame"):
        FrameSequence(frames=[b"too short"])
