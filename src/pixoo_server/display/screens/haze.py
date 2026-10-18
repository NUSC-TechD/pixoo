from __future__ import annotations

import asyncio
from datetime import date, datetime
from typing import Any

import httpx

from ..models import FrameSequence

PSI_URL = "https://api-open.data.gov.sg/v2/real-time/api/psi"
WEATHER_URL = "https://api-open.data.gov.sg/v2/real-time/api/twenty-four-hr-forecast"
REGIONS = {"north", "south", "east", "west", "central"}
SIZE = 64
ANIMATION_LEVELS = (0.70, 0.80, 0.90, 1.00, 1.00, 0.90, 0.80, 0.70)
FONT = {
    " ": ("000", "000", "000", "000", "000"),
    "-": ("000", "000", "111", "000", "000"),
    ".": ("000", "000", "000", "000", "010"),
    ":": ("000", "010", "000", "010", "000"),
    "0": ("111", "101", "101", "101", "111"),
    "1": ("010", "110", "010", "010", "111"),
    "2": ("111", "001", "111", "100", "111"),
    "3": ("111", "001", "111", "001", "111"),
    "4": ("101", "101", "111", "001", "001"),
    "5": ("111", "100", "111", "001", "111"),
    "6": ("111", "100", "111", "101", "111"),
    "7": ("111", "001", "010", "010", "010"),
    "8": ("111", "101", "111", "101", "111"),
    "9": ("111", "101", "111", "001", "111"),
    "A": ("010", "101", "111", "101", "101"),
    "B": ("110", "101", "110", "101", "110"),
    "C": ("111", "100", "100", "100", "111"),
    "D": ("110", "101", "101", "101", "110"),
    "E": ("111", "100", "110", "100", "111"),
    "F": ("111", "100", "110", "100", "100"),
    "G": ("111", "100", "101", "101", "111"),
    "H": ("101", "101", "111", "101", "101"),
    "I": ("111", "010", "010", "010", "111"),
    "J": ("001", "001", "001", "101", "111"),
    "K": ("101", "101", "110", "101", "101"),
    "L": ("100", "100", "100", "100", "111"),
    "M": ("101", "111", "111", "101", "101"),
    "N": ("101", "111", "111", "111", "101"),
    "O": ("111", "101", "101", "101", "111"),
    "P": ("111", "101", "111", "100", "100"),
    "Q": ("111", "101", "101", "111", "001"),
    "R": ("110", "101", "110", "101", "101"),
    "S": ("111", "100", "111", "001", "111"),
    "T": ("111", "010", "010", "010", "010"),
    "U": ("101", "101", "101", "101", "111"),
    "V": ("101", "101", "101", "101", "010"),
    "W": ("101", "101", "111", "111", "101"),
    "X": ("101", "101", "010", "101", "101"),
    "Y": ("101", "101", "010", "010", "010"),
    "Z": ("111", "001", "010", "100", "111"),
}


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
        frames = [
            render_frame(values[region], weather, animation_frame)
            for animation_frame in range(len(ANIMATION_LEVELS))
        ]
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


def render_frame(value: int, weather: dict[str, Any], animation_frame: int = 0) -> bytes:
    """Render one animation phase using the original pixel-art layout."""
    frame = bytearray((4, 8, 14) * (SIZE * SIZE))
    category, accent = psi_style(value)
    display_date = datetime.fromisoformat(weather["date"]).date()
    date_text = display_date.strftime("%a %d %b").upper()
    week = nus_week_label(display_date)
    heading = f"{week} {date_text}" if week else date_text
    level = ANIMATION_LEVELS[animation_frame]

    draw_centered(frame, heading, 2, (235, 240, 245))
    draw_centered(frame, "24H PSI", 10, (190, 205, 220))
    draw_centered(frame, str(value), 17, dim_color(accent, level), scale=3)
    draw_centered(frame, category, 34, accent)
    draw_weather_icon(frame, str(weather["forecast"]), animation_frame)
    temperature = f"{weather['low']}-{weather['high']}C"
    draw_text(
        frame,
        temperature,
        48 - text_width(temperature) // 2,
        47,
        (100, 195, 245),
    )
    draw_centered(
        frame,
        "TECHD X MAKERS",
        58,
        dim_color((235, 240, 245), 0.85 + 0.15 * level),
    )
    return bytes(frame)


def set_pixel(frame: bytearray, x: int, y: int, color: tuple[int, int, int]) -> None:
    """Set one RGB pixel when its coordinates are inside the display."""
    if 0 <= x < SIZE and 0 <= y < SIZE:
        offset = (y * SIZE + x) * 3
        frame[offset : offset + 3] = bytes(color)


def fill_rect(
    frame: bytearray,
    x: int,
    y: int,
    width: int,
    height: int,
    color: tuple[int, int, int],
) -> None:
    """Fill a rectangular region in a raw RGB frame."""
    for row in range(y, y + height):
        for column in range(x, x + width):
            set_pixel(frame, column, row, color)


def text_width(text: str, scale: int = 1) -> int:
    """Return the rendered width of text in the custom 3-by-5 font."""
    return max(0, len(text) * 4 * scale - scale)


def draw_text(
    frame: bytearray,
    text: str,
    x: int,
    y: int,
    color: tuple[int, int, int],
    scale: int = 1,
) -> None:
    """Draw text using the original custom pixel font."""
    cursor = x
    for character in text.upper():
        glyph = FONT.get(character, FONT[" "])
        for row, bits in enumerate(glyph):
            for column, bit in enumerate(bits):
                if bit == "1":
                    for dy in range(scale):
                        for dx in range(scale):
                            set_pixel(
                                frame,
                                cursor + column * scale + dx,
                                y + row * scale + dy,
                                color,
                            )
        cursor += 4 * scale


def draw_centered(
    frame: bytearray,
    text: str,
    y: int,
    color: tuple[int, int, int],
    scale: int = 1,
    x_offset: int = 0,
) -> None:
    """Draw custom-font text horizontally centered on the display."""
    draw_text(
        frame,
        text,
        (SIZE - text_width(text, scale)) // 2 + x_offset,
        y,
        color,
        scale,
    )


def dim_color(color: tuple[int, int, int], level: float) -> tuple[int, int, int]:
    """Scale an RGB color for the pulse animation."""
    return tuple(round(channel * level) for channel in color)


def nus_week_label(day: date) -> str:
    """Return the NUS teaching-week label used by the original screen."""
    first_block = datetime(2026, 8, 10).date()
    second_block = datetime(2026, 9, 28).date()
    if first_block <= day <= datetime(2026, 9, 18).date():
        return f"W{(day - first_block).days // 7 + 1}"
    if second_block <= day <= datetime(2026, 11, 13).date():
        return f"W{(day - second_block).days // 7 + 7}"
    return ""


def draw_cloud(frame: bytearray, x: int, y: int) -> None:
    """Draw the original outlined cloud pixel mask."""
    blue = (105, 155, 205)
    cloud = (225, 230, 228)
    mask = (
        "......BBBB............",
        ".....BWWWWWWW.........",
        ".....BWWWWWWWW.BBB....",
        ".....BWWWWWWWWBWWW....",
        "..BBBWWWWWWWWWBWWWWW..",
        ".BWWWWWWWWWWWBBWWWWWW.",
        ".BWWWWWWWWWWBWWWWWWWWW",
        ".BWWWWWWWWWWBWWWWWWWWW",
        ".BBWWWWWWWWWWWWWWWWWWW",
        "..BBBBBBBBBBBBBBBBBBBB.",
        "....BBBBBBBBBBBBBBB....",
    )
    for row, pixels in enumerate(mask):
        for column, pixel in enumerate(pixels):
            if pixel == "B":
                set_pixel(frame, x + column, y + row, blue)
            elif pixel == "W":
                set_pixel(frame, x + column, y + row, cloud)


def draw_weather_icon(frame: bytearray, forecast: str, animation_frame: int) -> None:
    """Draw the original animated icon selected from the forecast text."""
    condition = forecast.upper()
    x = 9
    y = 42
    yellow = dim_color((255, 205, 45), ANIMATION_LEVELS[animation_frame])

    if any(word in condition for word in ("HAZY", "MIST", "FOG")):
        fill_rect(frame, x + 7, y, 6, 6, yellow)
        for offset, width in ((7, 17), (10, 13)):
            fill_rect(frame, x + 2, y + offset, width, 2, (125, 160, 175))
    elif "WIND" in condition:
        for row, width in ((2, 15), (6, 19), (10, 12)):
            fill_rect(frame, x + 2, y + row, width, 2, (95, 205, 235))
    elif any(word in condition for word in ("RAIN", "SHOWER")):
        draw_cloud(frame, x, y)
        rain_y = y + 11 + animation_frame % 2
        for rain_x in (x + 5, x + 10, x + 15):
            set_pixel(frame, rain_x, rain_y, (65, 155, 255))
            set_pixel(frame, rain_x - 1, rain_y + 1, (65, 155, 255))
        if "THUNDER" in condition:
            fill_rect(frame, x + 10, y + 9, 2, 3, (255, 220, 40))
            set_pixel(frame, x + 9, y + 12, (255, 220, 40))
    elif "CLOUD" in condition:
        if "PARTLY" in condition:
            fill_rect(frame, x + 1, y, 6, 6, yellow)
        draw_cloud(frame, x, y + 2)
    else:
        fill_rect(frame, x + 7, y + 3, 7, 7, yellow)
        for sun_x, sun_y in ((10, 0), (10, 12), (4, 6), (16, 6)):
            set_pixel(frame, x + sun_x, y + sun_y, yellow)
