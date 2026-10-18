"""In-memory connection state for cloud-emulator health reporting."""

from __future__ import annotations

import time

from pydantic import BaseModel, ConfigDict


class DeviceStatus(BaseModel):
    """Track the transient MQTT connection state of one emulated cloud device.

    These values describe the current runtime session and recent activity.
    They are not persisted and are separate from the physical screen settings.
    """

    model_config = ConfigDict(validate_assignment=True)

    device_id: int
    client_id: str | None = None
    connected_at: float | None = None
    last_activity_at: float | None = None
    last_command: str | None = None
    disconnect_count: int = 0


class DeviceStore:
    """Maintain runtime connection status for every Pixoo cloud session.

    The MQTT broker records connections, activity, and disconnections here,
    while HTTP health routes read snapshots from it. The store deliberately
    does not persist data or define how screens are configured.
    """

    def __init__(self) -> None:
        self._devices: dict[int, DeviceStatus] = {}
        self.bootstrap_count = 0

    def bootstrap(self) -> None:
        self.bootstrap_count += 1

    def connected(self, device_id: int, client_id: str) -> None:
        now = time.monotonic()
        status = self._devices.setdefault(device_id, DeviceStatus(device_id=device_id))
        if status.client_id == client_id:
            status.last_activity_at = now
            return
        status.client_id = client_id
        status.connected_at = now
        status.last_activity_at = now

    def activity(self, device_id: int, command: str | None = None) -> None:
        status = self._devices.setdefault(device_id, DeviceStatus(device_id=device_id))
        status.last_activity_at = time.monotonic()
        if command:
            status.last_command = command

    def disconnected(self, device_id: int, client_id: str) -> None:
        status = self._devices.get(device_id)
        if not status or status.client_id != client_id:
            return
        status.client_id = None
        status.connected_at = None
        status.disconnect_count += 1

    def snapshot(self, inactivity_seconds: int = 45) -> dict[str, object]:
        now = time.monotonic()
        devices = []
        for status in self._devices.values():
            inactive_for = now - status.last_activity_at if status.last_activity_at else None
            connected = status.client_id is not None
            devices.append(
                {
                    "device_id": status.device_id,
                    "client_id": status.client_id,
                    "connected": connected,
                    "connected_for_seconds": now - status.connected_at
                    if status.connected_at
                    else None,
                    "inactive_for_seconds": inactive_for,
                    "last_command": status.last_command,
                    "disconnect_count": status.disconnect_count,
                    "healthy": connected
                    and inactive_for is not None
                    and inactive_for < inactivity_seconds,
                }
            )
        return {
            "status": "online" if any(device["healthy"] for device in devices) else "offline",
            "bootstrap_count": self.bootstrap_count,
            "devices": devices,
        }
