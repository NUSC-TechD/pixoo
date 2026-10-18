"""Encode and decode the MQTT packet subset used by Pixoo firmware."""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

from pydantic import BaseModel, ConfigDict

SET_TOPIC_PATTERN = re.compile(rb"divoom/2/(\d+)/set")


class ConnectInfo(BaseModel):
    """Carry the client identity extracted from an MQTT CONNECT packet.

    This immutable transfer object passes parsed connection fields from the
    wire-protocol module to the broker. It is not application or screen
    configuration.
    """

    model_config = ConfigDict(frozen=True)

    client_id: str
    password: str


async def read_packet(reader: asyncio.StreamReader) -> tuple[int, int, bytes]:
    first = (await reader.readexactly(1))[0]
    remaining = 0
    multiplier = 1
    for _ in range(4):
        byte = (await reader.readexactly(1))[0]
        remaining += (byte & 0x7F) * multiplier
        if not byte & 0x80:
            return first >> 4, first & 0x0F, await reader.readexactly(remaining)
        multiplier *= 128
    raise ValueError("Invalid MQTT remaining length")


def parse_connect(body: bytes) -> ConnectInfo:
    offset = 0
    _, offset = _read_string(body, offset)  # protocol name
    if len(body) < offset + 4:
        raise ValueError("Truncated CONNECT packet")
    offset += 1  # protocol level
    connect_flags = body[offset]
    offset += 3  # flags and keepalive
    client_id, offset = _read_string(body, offset)
    if connect_flags & 0x04:
        _, offset = _read_string(body, offset)  # will topic
        _, offset = _read_string(body, offset)  # will payload
    if connect_flags & 0x80:
        _, offset = _read_string(body, offset)
    password = ""
    if connect_flags & 0x40:
        password, offset = _read_string(body, offset)
    return ConnectInfo(client_id=client_id, password=password)


def parse_subscribe(body: bytes) -> tuple[int, list[str]]:
    if len(body) < 2:
        raise ValueError("Truncated SUBSCRIBE packet")
    packet_id = int.from_bytes(body[:2], "big")
    offset = 2
    topics = []
    while offset < len(body):
        topic, offset = _read_string(body, offset)
        if offset >= len(body):
            raise ValueError("Missing subscription QoS")
        offset += 1
        topics.append(topic)
    return packet_id, topics


def parse_publish(flags: int, body: bytes) -> tuple[str, bytes, int | None, int]:
    if len(body) < 2:
        raise ValueError("Truncated PUBLISH packet")
    qos = (flags >> 1) & 0x03
    declared_length = int.from_bytes(body[:2], "big")
    topic_end = 2 + declared_length
    if topic_end > len(body):
        match = SET_TOPIC_PATTERN.search(body, 2)
        if not match:
            raise ValueError("Malformed PUBLISH topic length")
        topic_start, topic_end = match.span()
    else:
        topic_start = 2
    topic = body[topic_start:topic_end].decode()
    offset = topic_end
    packet_id = None
    if qos:
        if len(body) < offset + 2:
            raise ValueError("Missing PUBLISH packet ID")
        packet_id = int.from_bytes(body[offset : offset + 2], "big")
        offset += 2
    return topic, body[offset:], packet_id, qos


def publish_packet(topic: str, payload: dict[str, Any]) -> bytes:
    topic_bytes = topic.encode()
    body = len(topic_bytes).to_bytes(2, "big") + topic_bytes + json.dumps(payload).encode()
    return control_packet(3, 0, body)


def control_packet(packet_type: int, flags: int, body: bytes) -> bytes:
    return bytes(((packet_type << 4) | flags,)) + encode_remaining_length(len(body)) + body


def encode_remaining_length(value: int) -> bytes:
    result = bytearray()
    while True:
        byte = value % 128
        value //= 128
        if value:
            byte |= 0x80
        result.append(byte)
        if not value:
            return bytes(result)


async def write_packet(writer: asyncio.StreamWriter, packet: bytes) -> None:
    writer.write(packet)
    await writer.drain()


def _read_string(body: bytes, offset: int) -> tuple[str, int]:
    if len(body) < offset + 2:
        raise ValueError("Truncated MQTT string")
    length = int.from_bytes(body[offset : offset + 2], "big")
    start = offset + 2
    end = start + length
    if end > len(body):
        raise ValueError("Truncated MQTT string")
    return body[start:end].decode(), end
