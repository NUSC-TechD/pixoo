import pytest
from pydantic import ValidationError

from pixoo_server.config.settings import Settings


def test_loads_toml_and_allows_environment_overrides(tmp_path, monkeypatch) -> None:
    config = tmp_path / "pixoo.toml"
    config.write_text(
        """
host_ip = "10.0.0.1"
http_port = 8000
device_id = 101

[[screens]]
name = "lobby"
address = "10.0.0.8"

[[screens.views]]
type = "haze"
region = "central"
"""
    )
    monkeypatch.setenv("HTTP_PORT", "9000")

    settings = Settings.load(config)

    assert settings.host_ip == "10.0.0.1"
    assert settings.http_port == 9000
    assert settings.device_id == 101
    assert settings.screens[0].name == "lobby"
    assert settings.screens[0].views[0].options == {"region": "central"}


def test_rejects_invalid_ports_and_duplicate_screens() -> None:
    with pytest.raises(ValidationError, match="less than or equal to 65535"):
        Settings(http_port=70_000)

    duplicate = {
        "name": "lobby",
        "address": "10.0.0.8",
        "views": [{"type": "haze"}],
    }
    with pytest.raises(ValidationError, match="Screen names must be unique"):
        Settings(screens=[duplicate, duplicate])
