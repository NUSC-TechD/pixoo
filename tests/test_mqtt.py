import asyncio
import json

from pixoo_server.cloud_emulator.responses import device_response
from pixoo_server.cloud_emulator.state import DeviceStore
from pixoo_server.mqtt.broker import MqttBroker
from pixoo_server.mqtt.protocol import (
    control_packet,
    encode_remaining_length,
    parse_publish,
    publish_packet,
    read_packet,
)


def test_parses_normal_and_malformed_pixoo_publish() -> None:
    topic = b"divoom/2/12345/set"
    payload = json.dumps({"Command": "Device/Connect"}).encode()
    packet_id = b"\x00\x07"
    normal = len(topic).to_bytes(2, "big") + topic + packet_id + payload
    malformed = (999).to_bytes(2, "big") + topic + packet_id + payload

    assert parse_publish(0b0100, normal) == (topic.decode(), payload, 7, 2)
    assert parse_publish(0b0100, malformed) == (topic.decode(), payload, 7, 2)


def test_builds_multi_byte_remaining_length_and_publish() -> None:
    assert encode_remaining_length(321) == bytes((193, 2))
    packet = publish_packet("divoom/2/12345/get", {"ok": "x" * 200})
    assert packet[0] == 0x30
    assert packet[1] & 0x80


def test_returns_captured_startup_response_shapes() -> None:
    response = device_response(
        {"Command": "Sys/GetConf", "DeviceId": 12345, "PacketFlag": "3"},
        12345,
    )
    assert response["PacketFlag"] == 3
    assert response["Brightness"] == 100
    assert response["TimeZoneName"] == "UTC"

    schedule = device_response({"Command": "Channel/GetAllCustomTime"}, 12345)
    assert len(schedule["TimeList"]) == 3
    assert all(item["IsEnable"] == 0 for item in schedule["TimeList"])


def test_broker_handles_firmware_session() -> None:
    async def scenario() -> None:
        devices = DeviceStore()
        broker = MqttBroker(0, devices)
        await broker.start()
        reader, writer = await asyncio.open_connection("127.0.0.1", broker.bound_port)
        try:
            writer.write(_connect_packet("pixoo-test", "pixoopal"))
            await writer.drain()
            assert await reader.readexactly(4) == bytes((0x20, 0x02, 0x00, 0x00))

            topic = b"divoom/2/12345/get"
            heartbeat_topic = b"divoom/2/DeviceHeart"
            subscribe_body = (
                b"\x00\x01"
                + len(topic).to_bytes(2, "big")
                + topic
                + b"\x00"
                + len(heartbeat_topic).to_bytes(2, "big")
                + heartbeat_topic
                + b"\x00"
            )
            writer.write(control_packet(8, 2, subscribe_body))
            await writer.drain()
            assert await read_packet(reader) == (9, 0, b"\x00\x01\x00\x00")
            packet_type, _, _ = await read_packet(reader)
            assert packet_type == 3  # initial heartbeat

            set_topic = b"divoom/2/12345/set"
            payload = json.dumps(
                {"Command": "Device/Connect", "DeviceId": 12345, "PacketFlag": 2}
            ).encode()
            publish_body = len(set_topic).to_bytes(2, "big") + set_topic + b"\x00\x02" + payload
            writer.write(control_packet(3, 4, publish_body))
            await writer.drain()
            assert await read_packet(reader) == (5, 0, b"\x00\x02")
            response_type, response_flags, response_body = await read_packet(reader)
            response_topic, response_payload, _, _ = parse_publish(response_flags, response_body)
            assert response_type == 3
            assert response_topic == "divoom/2/12345/get"
            assert json.loads(response_payload)["Command"] == "Device/Connect"
            assert devices.snapshot()["status"] == "online"
        finally:
            writer.write(bytes((0xE0, 0x00)))
            await writer.drain()
            await asyncio.wait_for(reader.read(), timeout=1)
            writer.close()
            await writer.wait_closed()
            await broker.stop()

    asyncio.run(scenario())


def _connect_packet(client_id: str, password: str) -> bytes:
    def mqtt_string(value: str) -> bytes:
        encoded = value.encode()
        return len(encoded).to_bytes(2, "big") + encoded

    body = (
        mqtt_string("MQTT")
        + bytes((4, 0x42, 0, 30))
        + mqtt_string(client_id)
        + mqtt_string(password)
    )
    return control_packet(1, 0, body)
