from fastapi.testclient import TestClient

from pixoo_server.config.models import PixooConfig, ViewConfig
from pixoo_server.config.settings import Settings
from pixoo_server.main import create_app


def settings() -> Settings:
    return Settings(
        host_ip="10.42.0.1",
        public_ip="203.0.113.10",
        http_port=8080,
        mqtt_port=1883,
        device_id=222,
        api_key=None,
        screens=(
            PixooConfig(
                name="makerspace",
                address="10.42.0.8",
                views=[ViewConfig(type="haze")],
            ),
        ),
    )


def test_cloud_bootstrap_uses_global_device_id() -> None:
    with TestClient(create_app(settings(), enable_services=False)) as client:
        ip_response = client.get("/Test/GetIP")
        init_response = client.request(
            "GET",
            "/Device/InitV2",
            json={"PacketFlag": 7},
        )
        update_response = client.post(
            "/Device/UpdateDevicePublicIP",
            json={"DeviceId": 222, "PacketFlag": 8},
        )

    assert ip_response.json() == {
        "ReturnCode": 0,
        "ReturnMessage": "",
        "CustonIP": "203.0.113.10",
    }
    assert init_response.json()["DeviceId"] == 222
    assert init_response.json()["IP"] == "10.42.0.1"
    assert init_response.json()["PacketFlag"] == 7
    assert update_response.json()["PacketFlag"] == 8


def test_health_and_screen_status_are_available_without_hardware() -> None:
    app = create_app(settings(), enable_services=False)
    app.state.scheduler._animations["makerspace"] = b"GIF89a"

    with TestClient(app) as client:
        assert client.get("/health/live").json() == {"status": "ok"}
        health = client.get("/health")
        screens = client.get("/api/screens")
        animation = client.get("/api/screens/makerspace/animation.gif")

    assert health.status_code == 503
    assert health.json()["status"] == "offline"
    assert screens.status_code == 200
    assert screens.json()[0]["name"] == "makerspace"
    assert animation.status_code == 200
    assert animation.headers["content-type"] == "image/gif"
    assert animation.content == b"GIF89a"
