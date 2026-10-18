from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from pixoo_server.cloud_emulator.responses import device_response
from pixoo_server.cloud_emulator.state import DeviceStore

from .protocol import (
    SET_TOPIC_PATTERN,
    control_packet,
    parse_connect,
    parse_publish,
    parse_subscribe,
    publish_packet,
    read_packet,
    write_packet,
)

logger = logging.getLogger(__name__)
HEARTBEAT_TOPIC = "divoom/2/DeviceHeart"
GET_TOPIC_PATTERN = re.compile(r"divoom/2/(\d+)/get")


class MqttBroker:
    """Serve the small MQTT subset required by Pixoo cloud bootstrapping.

    The broker accepts device sessions, checks their password, handles the
    subscribe, publish, acknowledgement, ping, and heartbeat flows used by
    Pixoo firmware, and records activity in :class:`DeviceStore`. It is an
    application-specific compatibility service, not a general MQTT broker.
    """

    def __init__(self, port: int, devices: DeviceStore, password: str = "pixoopal") -> None:
        self.port = port
        self.devices = devices
        self.password = password
        self._server: asyncio.Server | None = None
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._heartbeat_writers: set[asyncio.StreamWriter] = set()

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._handle_client, "0.0.0.0", self.port)
        self._heartbeat_task = asyncio.create_task(
            self._publish_heartbeats(), name="mqtt-heartbeats"
        )
        logger.info("MQTT listening on 0.0.0.0:%s", self.port)

    async def stop(self) -> None:
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            await asyncio.gather(self._heartbeat_task, return_exceptions=True)
        if self._server:
            self._server.close()
            await self._server.wait_closed()

    @property
    def bound_port(self) -> int:
        if not self._server or not self._server.sockets:
            raise RuntimeError("MQTT broker is not running")
        return int(self._server.sockets[0].getsockname()[1])

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        client_id = "unknown"
        device_id: int | None = None
        peer = writer.get_extra_info("peername")
        try:
            packet_type, flags, body = await read_packet(reader)
            if packet_type != 1:
                raise ValueError("First MQTT packet must be CONNECT")
            connect = parse_connect(body)
            client_id = connect.client_id
            accepted = not connect.password or connect.password == self.password
            await write_packet(writer, bytes((0x20, 0x02, 0x00, 0x00 if accepted else 0x04)))
            if not accepted:
                return
            logger.info("Pixoo connected: client=%s peer=%s", client_id, peer)

            while True:
                packet_type, flags, body = await read_packet(reader)
                if packet_type == 3:
                    topic, payload, packet_id, qos = parse_publish(flags, body)
                    matched = SET_TOPIC_PATTERN.fullmatch(topic.encode())
                    if matched:
                        device_id = int(matched.group(1))
                        self.devices.connected(device_id, client_id)
                    if qos == 1 and packet_id:
                        await write_packet(
                            writer, control_packet(4, 0, packet_id.to_bytes(2, "big"))
                        )
                    elif qos == 2 and packet_id:
                        await write_packet(
                            writer, control_packet(5, 0, packet_id.to_bytes(2, "big"))
                        )
                    if matched:
                        await self._handle_publish(writer, device_id, payload)
                elif packet_type == 6:
                    await write_packet(writer, control_packet(7, 0, body[:2]))
                elif packet_type == 8:
                    packet_id, topics = parse_subscribe(body)
                    await write_packet(
                        writer,
                        control_packet(9, 0, packet_id.to_bytes(2, "big") + bytes(len(topics))),
                    )
                    for topic in topics:
                        matched = GET_TOPIC_PATTERN.fullmatch(topic)
                        if matched:
                            device_id = int(matched.group(1))
                            self.devices.connected(device_id, client_id)
                    if HEARTBEAT_TOPIC in topics:
                        self._heartbeat_writers.add(writer)
                        await write_packet(
                            writer,
                            publish_packet(HEARTBEAT_TOPIC, {"Command": "Device/Hearbeat"}),
                        )
                elif packet_type == 12:
                    if device_id:
                        self.devices.activity(device_id)
                    await write_packet(writer, bytes((0xD0, 0x00)))
                elif packet_type == 14:
                    return
        except (asyncio.IncompleteReadError, ConnectionError):
            pass
        except Exception:
            logger.exception("MQTT client failed: client=%s peer=%s", client_id, peer)
        finally:
            self._heartbeat_writers.discard(writer)
            if device_id is not None:
                self.devices.disconnected(device_id, client_id)
            writer.close()
            await writer.wait_closed()
            logger.info("Pixoo disconnected: client=%s", client_id)

    async def _publish_heartbeats(self) -> None:
        while True:
            await asyncio.sleep(60)
            packet = publish_packet(HEARTBEAT_TOPIC, {"Command": "Device/Hearbeat"})
            for writer in tuple(self._heartbeat_writers):
                try:
                    await write_packet(writer, packet)
                except (ConnectionError, RuntimeError):
                    self._heartbeat_writers.discard(writer)

    async def _handle_publish(
        self, writer: asyncio.StreamWriter, device_id: int, payload: bytes
    ) -> None:
        try:
            body = json.loads(payload)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return
        command = body.get("Command")
        if not isinstance(command, str):
            return
        self.devices.activity(device_id, command)
        if command == "Device/Hearbeat":
            response = {
                "Command": command,
                "DeviceId": _number(body.get("DeviceId"), device_id),
                "PacketFlag": _number(body.get("PacketFlag"), 0),
            }
        else:
            response = device_response(body, device_id)
        await write_packet(writer, publish_packet(f"divoom/2/{device_id}/get", response))


def _number(value: Any, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback
