"""Captured cloud-emulator responses for Pixoo firmware commands."""

from __future__ import annotations

from typing import Any


def device_response(body: dict[str, Any], default_device_id: int) -> dict[str, Any]:
    command = body.get("Command", "")
    base = {
        "ReturnCode": 0,
        "ReturnMessage": "",
        "DeviceId": _number(body.get("DeviceId"), default_device_id),
        "Command": command,
        "PacketFlag": _number(body.get("PacketFlag"), 0),
    }
    disabled_schedule = {
        "IsEnable": 0,
        "StartTime": 32400,
        "EndTime": 36000,
        "VoiceEnable": 0,
        "WeekArray": [0, 0, 0, 0, 0, 0, 0],
    }
    if command == "Device/BindUser":
        return {**base, "NewHost": 1}
    if command == "Device/Connect":
        return {
            **base,
            "Software": _number(body.get("Software"), 0),
            "LocalToken": 0,
            "ExpertList": [],
        }
    if command == "Device/GetAppIP":
        return {**base, "AppIpList": []}
    if command in {"Device/GetCustomGalleryTimeList", "Device/GetSubscribeGalleryTimeList"}:
        return {**base, "TimeList": []}
    if command == "Channel/GetNightView":
        return {**base, "OnOff": 0, "StartTime": 0, "EndTime": 360, "Brightness": 50}
    if command == "Channel/GetAllCustomTime":
        return {**base, "TimeList": [disabled_schedule.copy() for _ in range(3)]}
    if command in {"Channel/GetEqTime", "Channel/GetSubscribeTime"}:
        return {**base, **disabled_schedule}
    if command == "Channel/OnOffScreen":
        return {key: value for key, value in base.items() if key != "Command"}

    empty_lists = {
        "Device/GetUserDefineList": {"AllFlag": 1, "HasNum": 0, "FileList": [], "FileNum": 0},
        "Device/GetHotList": {"FileList": [], "FileNum": 0},
        "Device/GetTimePlan": {"IsEnable": 0, "TimePlanUpdateTime": 0, "PlanItem": []},
        "Device/GetAlarm": {"AlarmList": []},
        "Device/GetMemorial": {"MemorialList": []},
        "Device/GetTimeDialFont": {"FontList": []},
        "Device/GetTimeDialAppPic": {"PicList": []},
        "Device/GetClockList": {"ClockList": []},
        "Device/GetEqDataList": {"EqDataList": []},
        "Channel/GetNotifyList": {"NotifyList": []},
        "Device/GetHistoryClockList": {"HistoryClockList": []},
    }
    if command in empty_lists:
        return {**base, **empty_lists[command]}
    if command in {"Weather/GetRealWeatherInfo", "Weather/GetForecastWeatherInfo"}:
        return {**base, "expire": 1}
    if command == "Sys/GetConf":
        return {**base, **_system_config()}
    return base


def _number(value: Any, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _system_config() -> dict[str, Any]:
    return {
        "CurClockId": 0,
        "OnOff": 0,
        "StartTime": 0,
        "EndTime": 360,
        "Brightness": 100,
        "ChannelIndex": 0,
        "RotationFlag": 0,
        "ClockTime": 60,
        "GalleryTime": 60,
        "SingleGalleyTime": -1,
        "GalleryShowTimeFlag": -1,
        "Time24Flag": 0,
        "LocationMode": 0,
        "LocationCityName": "",
        "LocationCityId": 0,
        "Longitude": 0,
        "Latitude": 0,
        "TimeZoneMode": 0,
        "TimeZoneInfo": 0,
        "TemperatureMode": 0,
        "StartupFileId": "",
        "GyrateAngle": 0,
        "DeviceAutoUpdate": 0,
        "TimeZoneName": "UTC",
        "TimeZoneValue": "UTC0",
        "WhiteBalanceR": 100,
        "WhiteBalanceG": 100,
        "WhiteBalanceB": 100,
        "MirrorFlag": 0,
        "HighLight": 0,
        "DateFormat": 0,
        "LcdImageArray": ["", "", "", "", ""],
        "StartUpClockId": 0,
        "OnOffVolume": 1,
        "NotificationSound": 80,
        "BluetoothAutoConnect": 1,
        "AutoPowerOff": 0,
        "DisableMic": 0,
        "Language": 0,
        "ScreenProtection": 0,
        "LockScreenTime": 600,
        "ShowGrid1632": 1,
        "ColorTemp": 0,
        "Wind": 0,
        "StartUpClockOnOff": 0,
        "SoundEffectMode": 1,
    }
