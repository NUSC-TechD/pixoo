from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

import httpx
from PIL import Image, ImageDraw, ImageFont

from ..models import FrameSequence

PSI_URL = "https://api-open.data.gov.sg/v2/real-time/api/psi"
WEATHER_URL = "https://api-open.data.gov.sg/v2/real-time/api/twenty-four-hr-forecast"
REGIONS = {"north", "south", "east", "west", "central"}
ANIMATION_LEVELS = (0.70, 0.80, 0.90, 1.00, 1.00, 0.90, 0.80, 0.70)


class HazeScreen:
    """Render Singapore haze and weather readings as a 64-by-64 animation.

    This screen fetches PSI and forecast data from data.gov.sg for the view's
    configured region, then converts the result into a :class:`FrameSequence`.
    It only creates content; it neither selects a screen nor uploads frames.
    """

    def __init__(self, api_key: str | None = None) -> None:
        self._headers = {"Accept": "application/json", "User-Agent": "nusc-pixoo/0.1"}
        if api_key:
            self._headers["x-api-key"] = api_key

    async def render(self, client: httpx.AsyncClient, options: dict[str, Any]) -> FrameSequence:
        region = str(options.get("region", "west")).lower()
        if region not in REGIONS:
            raise ValueError(f"Unknown PSI region: {region}")
        psi_response, weather_response = await asyncio.gather(
            client.get(PSI_URL, headers=self._headers),
            client.get(WEATHER_URL, headers=self._headers),
        )
        psi_response.raise_for_status()
        weather_response.raise_for_status()
        values, timestamp = parse_psi(psi_response.json())
        weather = parse_weather(weather_response.json(), region)
        frames = [render_frame(values[region], weather, level) for level in ANIMATION_LEVELS]
        return FrameSequence(frames=frames, speed_ms=250)


def parse_psi(payload: dict[str, Any]) -> tuple[dict[str, int], str]:
    if payload.get("code") != 0:
        raise ValueError(payload.get("errorMsg") or "data.gov.sg returned a PSI error")
    try:
        item = payload["data"]["items"][0]
        readings = item["readings"]["psi_twenty_four_hourly"]
        return {region: int(readings[region]) for region in REGIONS}, item["timestamp"]
    except (KeyError, IndexError, TypeError, ValueError) as error:
        raise ValueError("Unexpected PSI response from data.gov.sg") from error


def parse_weather(payload: dict[str, Any], region: str) -> dict[str, Any]:
    if payload.get("code") != 0:
        raise ValueError(payload.get("errorMsg") or "data.gov.sg returned a weather error")
    try:
        record = payload["data"]["records"][0]
        reading_time = datetime.fromisoformat(record["timestamp"])
        current_period = next(
            (
                period
                for period in record["periods"]
                if datetime.fromisoformat(period["timePeriod"]["start"])
                <= reading_time
                < datetime.fromisoformat(period["timePeriod"]["end"])
            ),
            record["periods"][0],
        )
        temperature = record["general"]["temperature"]
        return {
            "forecast": current_period["regions"][region]["text"],
            "low": int(temperature["low"]),
            "high": int(temperature["high"]),
            "date": record["general"]["validPeriod"]["start"],
        }
    except (KeyError, IndexError, StopIteration, TypeError, ValueError) as error:
        raise ValueError("Unexpected weather response from data.gov.sg") from error


def psi_style(value: int) -> tuple[str, tuple[int, int, int]]:
    if value <= 50:
        return "GOOD", (40, 210, 100)
    if value <= 100:
        return "MODERATE", (245, 210, 55)
    if value <= 200:
        return "UNHEALTHY", (255, 125, 35)
    if value <= 300:
        return "VERY UNHEALTHY", (245, 45, 55)
    return "HAZARDOUS", (170, 55, 210)


def render_frame(value: int, weather: dict[str, Any], level: float = 1.0) -> bytes:
    image = Image.new("RGB", (64, 64), (4, 8, 14))
    draw = ImageDraw.Draw(image)
    small = ImageFont.load_default(size=7)
    medium = ImageFont.load_default(size=9)
    large = ImageFont.load_default(size=20)
    category, accent = psi_style(value)
    display_date = datetime.fromisoformat(weather["date"]).strftime("%a %d %b").upper()

    _center(draw, display_date, 1, (235, 240, 245), small)
    _center(draw, "24H PSI", 9, (190, 205, 220), small)
    _center(draw, str(value), 14, _dim(accent, level), large)
    _center(draw, category, 34, accent, small)
    _draw_weather_icon(draw, str(weather["forecast"]), level)
    _center(draw, f"{weather['low']}-{weather['high']}C", 47, (100, 195, 245), medium, x=12)
    _center(draw, "TECHD X MAKERS", 57, _dim((235, 240, 245), 0.85 + 0.15 * level), small)
    return image.tobytes()


def _center(
    draw: ImageDraw.ImageDraw,
    text: str,
    y: int,
    fill: tuple[int, int, int],
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    *,
    x: int = 32,
) -> None:
    box = draw.textbbox((0, 0), text, font=font)
    draw.text((x - (box[2] - box[0]) // 2, y), text, fill=fill, font=font)


def _draw_weather_icon(draw: ImageDraw.ImageDraw, forecast: str, level: float) -> None:
    condition = forecast.upper()
    yellow = _dim((255, 205, 45), level)
    if any(word in condition for word in ("RAIN", "SHOWER", "THUNDER")):
        draw.ellipse((3, 44, 18, 54), fill=(205, 220, 225), outline=(105, 155, 205))
        for x in (6, 11, 16):
            draw.line((x, 54, x - 1, 57), fill=(65, 155, 255))
    elif any(word in condition for word in ("HAZY", "MIST", "FOG")):
        draw.ellipse((7, 42, 14, 49), fill=yellow)
        draw.line((3, 51, 19, 51), fill=(125, 160, 175), width=2)
        draw.line((5, 55, 17, 55), fill=(125, 160, 175), width=2)
    elif "CLOUD" in condition:
        draw.ellipse((3, 45, 19, 56), fill=(220, 228, 230), outline=(105, 155, 205))
    else:
        draw.ellipse((6, 45, 17, 56), fill=yellow)


def _dim(color: tuple[int, int, int], level: float) -> tuple[int, int, int]:
    return tuple(round(channel * level) for channel in color)
