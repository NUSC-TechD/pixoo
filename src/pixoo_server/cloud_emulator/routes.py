"""HTTP routes used by Pixoo firmware to reach the cloud emulator."""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response, status

from pixoo_server.config.settings import Settings

from .state import DeviceStore

MAX_BODY_BYTES = 64 * 1024


def cloud_router(settings: Settings, devices: DeviceStore) -> APIRouter:
    router = APIRouter()

    @router.api_route("/Test/GetIP", methods=["GET", "POST"])
    async def get_ip() -> dict[str, Any]:
        devices.bootstrap()
        return {"ReturnCode": 0, "ReturnMessage": "", "CustonIP": settings.public_ip}

    @router.api_route("/Device/InitV2", methods=["GET", "POST"])
    async def initialize(request: Request) -> dict[str, Any]:
        body = await _json_body(request)
        packet_flag = _number(body.get("PacketFlag"), 0)
        now = int(time.time())
        return {
            "ReturnCode": 0,
            "ReturnMessage": "",
            "MqttPort": settings.mqtt_port,
            "DevicePublicIP": settings.public_ip,
            "IP": settings.host_ip,
            "BackupIP": settings.host_ip,
            "lot": 0,
            "lat": 0,
            "SummerZone": 0,
            "TimeZoneCode": "UTC",
            "UTCTime": now,
            "DeviceId": settings.device_id,
            "UserId": _number(body.get("BindUserId"), 0),
            "LogLevel": 0,
            "IsResetAll": 1,
            "DeviceToken": "pixoopal",
            "ServerType": 1,
            "LastClockId": 0,
            "OfflineTime": 0,
            "OnlineTime": now,
            "ScreenOnOff": 1,
            "CustomType": 0,
            "IsNewDevice": 0,
            "Command": "Device/InitV2",
            "PacketFlag": packet_flag,
        }

    @router.api_route("/Device/UpdateDevicePublicIP", methods=["GET", "POST"])
    async def update_public_ip(request: Request) -> dict[str, Any]:
        body = await _json_body(request)
        return {
            "ReturnCode": 0,
            "ReturnMessage": "",
            "DevicePublicIP": settings.public_ip,
            "expire": 1,
            "DeviceId": _number(body.get("DeviceId"), settings.device_id),
            "Command": "Device/UpdateDevicePublicIP",
            "PacketFlag": _number(body.get("PacketFlag"), 0),
        }

    @router.get("/health/live")
    async def live() -> dict[str, str]:
        return {"status": "ok"}

    @router.get("/health")
    async def health(response: Response) -> dict[str, object]:
        snapshot = devices.snapshot()
        if snapshot["status"] != "online":
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return snapshot

    return router


async def _json_body(request: Request) -> dict[str, Any]:
    body = await request.body()
    if len(body) > MAX_BODY_BYTES:
        raise HTTPException(status_code=413, detail="Request body is too large")
    if not body:
        return {}
    try:
        value = await request.json()
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def _number(value: Any, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback
