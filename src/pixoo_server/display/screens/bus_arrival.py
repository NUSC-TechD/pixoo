"""Render live NUS shuttle arrivals for a single bus stop."""

from __future__ import annotations

import logging
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ..drawing import draw_centered, draw_text, fill_rect, new_frame, text_width
from ..models import FrameSequence
from .unavailable import render_unavailable as render_unavailable_notice

logger = logging.getLogger(__name__)

ROUTE_COLORS = {
    "D1": (210, 90, 230),
    "D2": (145, 25, 145),
    "P": (120, 125, 130),
    "R1": (210, 100, 35),
    "R2": (0, 135, 35),
}


class BusTiming(BaseModel):
    """Represent the next two arrival estimates for one shuttle route."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    name: str
    arrival_time: str = Field(alias="arrivalTime")
    next_arrival_time: str = Field(alias="nextArrivalTime")


class BusStopTimings(BaseModel):
    """Represent all route timings returned for one NUS bus stop."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    bus_stop_name: str = Field(alias="busStopName")
    bus_stop_caption: str = Field(alias="busStopCaption")
    timings: list[BusTiming]


class BusArrivalResponse(BaseModel):
    """Validate the response envelope returned by the NUS bus proxy."""

    model_config = ConfigDict(extra="ignore")

    etas: BusStopTimings


class BusArrivalScreen:
    """Fetch and render two upcoming arrivals for every route at a bus stop.

    The screen uses a compact 64-by-64 layout with route-color markers and two
    ETA columns. It only renders content; the display scheduler controls when
    the resulting frame is encoded and uploaded to the physical Pixoo.
    Failed requests produce an animated unavailable-data view so other content
    can continue refreshing. The next scheduled render retries the request.
    """

    def __init__(self, api_base_url: str) -> None:
        self._api_base_url = api_base_url.rstrip("/")

    async def render(self, client: httpx.AsyncClient, options: dict[str, Any]) -> FrameSequence:
        stop = str(options.get("stop", "UTOWN")).upper()
        try:
            response = await client.get(
                f"{self._api_base_url}/{stop}",
                headers={"Accept": "application/json", "User-Agent": "nusc-pixoo/0.1"},
            )
            response.raise_for_status()
            arrivals = parse_bus_arrivals(response.json())
        except (httpx.HTTPError, ValueError) as error:
            logger.warning("Bus arrivals unavailable for %s: %s", stop, error)
            return render_unavailable(stop)
        return FrameSequence(frames=[render_frame(arrivals)], speed_ms=250)


def render_unavailable(stop: str) -> FrameSequence:
    """Show the shared unavailable-data animation for a bus stop."""
    return render_unavailable_notice(f"{stop} BUS"[:10])


def parse_bus_arrivals(payload: dict[str, Any]) -> BusStopTimings:
    """Validate and unwrap a bus proxy response."""
    try:
        return BusArrivalResponse.model_validate(payload).etas
    except ValidationError as error:
        raise ValueError("Unexpected response from the NUS bus API") from error


def format_eta(value: str) -> str:
    """Format one API arrival value for the compact pixel display."""
    cleaned = value.strip().upper()
    if cleaned in {"", "-"}:
        return "-"
    if cleaned in {"0", "ARR", "ARRIVING"}:
        return "ARR"
    return f"{cleaned}M" if cleaned.isdigit() else cleaned[:4]


def render_frame(arrivals: BusStopTimings) -> bytes:
    """Render one static bus-arrival frame with two ETAs per route."""
    frame = new_frame()
    draw_centered(frame, f"{arrivals.bus_stop_name} BUS"[:10], 2, (235, 240, 245))
    fill_rect(frame, 2, 9, 60, 1, (35, 45, 55))

    for index, timing in enumerate(arrivals.timings[:5]):
        y = 13 + index * 10
        color = ROUTE_COLORS.get(timing.name, (85, 145, 220))
        fill_rect(frame, 2, y - 1, 2, 7, color)
        draw_text(frame, timing.name[:2], 7, y, (235, 240, 245))
        draw_eta(frame, format_eta(timing.arrival_time), 31, y, (235, 240, 245))
        draw_eta(frame, format_eta(timing.next_arrival_time), 54, y, (135, 145, 155))
        if index < 4:
            fill_rect(frame, 2, y + 7, 60, 1, (20, 28, 36))

    return bytes(frame)


def draw_eta(
    frame: bytearray,
    text: str,
    center_x: int,
    y: int,
    color: tuple[int, int, int],
) -> None:
    """Draw one ETA centered around its fixed column position."""
    draw_text(frame, text, center_x - text_width(text) // 2, y, color)
