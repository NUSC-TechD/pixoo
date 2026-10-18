import asyncio

import httpx

from pixoo_server.display.screens.bus_arrival import (
    BusArrivalScreen,
    format_eta,
    parse_bus_arrivals,
    render_frame,
)


def bus_payload() -> dict[str, object]:
    return {
        "etas": {
            "lastUpdated": "2026-10-18T21:44:07+08:00",
            "busStopName": "UTOWN",
            "busStopCaption": "University Town",
            "timings": [
                {"name": "D1", "arrivalTime": "10", "nextArrivalTime": "35"},
                {"name": "D2", "arrivalTime": "13", "nextArrivalTime": "28"},
                {"name": "P", "arrivalTime": "-", "nextArrivalTime": "-"},
                {"name": "R1", "arrivalTime": "-", "nextArrivalTime": "-"},
                {"name": "R2", "arrivalTime": "-", "nextArrivalTime": "-"},
            ],
        },
        "degraded": False,
    }


def test_parses_two_arrivals_and_renders_all_utown_routes() -> None:
    arrivals = parse_bus_arrivals(bus_payload())
    frame = render_frame(arrivals)

    assert arrivals.bus_stop_name == "UTOWN"
    assert arrivals.timings[0].arrival_time == "10"
    assert arrivals.timings[0].next_arrival_time == "35"
    assert len(frame) == 64 * 64 * 3
    assert len(set(frame)) > 10


def test_formats_arrivals_for_the_pixel_display() -> None:
    assert format_eta("10") == "10M"
    assert format_eta("0") == "ARR"
    assert format_eta("-") == "-"


def test_screen_fetches_the_configured_stop() -> None:
    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url == "https://bus.example/api/stop/UTOWN"
            return httpx.Response(200, json=bus_payload())

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            sequence = await BusArrivalScreen("https://bus.example/api/stop").render(
                client, {"stop": "utown"}
            )

        assert len(sequence.frames) == 1
        assert sequence.speed_ms == 250

    asyncio.run(run())
