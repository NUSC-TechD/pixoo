import asyncio

import httpx
import pytest

from pixoo_server.display.screens.bus_arrival import (
    BusArrivalScreen,
    BusStopTimings,
    BusTiming,
    format_eta,
    parse_bus_arrivals,
    render_frame,
    render_unavailable,
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


def test_routes_render_in_id_order_not_arrival_order() -> None:
    by_arrival = BusStopTimings(
        busStopName="UTOWN",
        busStopCaption="University Town",
        timings=[
            BusTiming(name="R2", arrivalTime="1", nextArrivalTime="20"),
            BusTiming(name="D2", arrivalTime="3", nextArrivalTime="18"),
            BusTiming(name="D1", arrivalTime="10", nextArrivalTime="35"),
            BusTiming(name="R1", arrivalTime="12", nextArrivalTime="30"),
            BusTiming(name="P", arrivalTime="-", nextArrivalTime="-"),
        ],
    )
    by_id = BusStopTimings(
        busStopName="UTOWN",
        busStopCaption="University Town",
        timings=[
            BusTiming(name="D1", arrivalTime="10", nextArrivalTime="35"),
            BusTiming(name="D2", arrivalTime="3", nextArrivalTime="18"),
            BusTiming(name="P", arrivalTime="-", nextArrivalTime="-"),
            BusTiming(name="R1", arrivalTime="12", nextArrivalTime="30"),
            BusTiming(name="R2", arrivalTime="1", nextArrivalTime="20"),
        ],
    )

    assert render_frame(by_arrival) == render_frame(by_id)


def test_formats_arrivals_for_the_pixel_display() -> None:
    assert format_eta("10") == "10M"
    assert format_eta("0") == "ARR"
    assert format_eta("-") == "-"


def test_screen_fetches_the_configured_stop() -> None:
    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url == "https://bus.example/api/stop/UTOWN"
            assert request.headers["user-agent"] == "nusc-pixoo/0.1"
            assert request.headers["accept"] == "application/json"
            return httpx.Response(200, json=bus_payload())

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            sequence = await BusArrivalScreen("https://bus.example/api/stop").render(
                client, {"stop": "utown"}
            )

        assert len(sequence.frames) == 1
        assert sequence.speed_ms == 250

    asyncio.run(run())


@pytest.mark.parametrize("failure", ["timeout", "http_error", "invalid_json", "invalid_payload"])
def test_api_failures_show_animated_fallback_and_recover(failure: str, caplog) -> None:
    async def run() -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            if calls > 1:
                return httpx.Response(200, json=bus_payload())
            if failure == "timeout":
                raise httpx.ReadTimeout("Bus API timed out", request=request)
            if failure == "http_error":
                return httpx.Response(503)
            if failure == "invalid_json":
                return httpx.Response(200, text="not JSON")
            return httpx.Response(200, json={"error": "Unavailable"})

        screen = BusArrivalScreen("https://bus.example/api/stop")
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            fallback = await screen.render(client, {"stop": "UTOWN"})
            recovered = await screen.render(client, {"stop": "UTOWN"})

        assert fallback == render_unavailable("UTOWN")
        assert recovered.frames == [render_frame(parse_bus_arrivals(bus_payload()))]
        assert calls == 2
        assert "Bus arrivals unavailable for UTOWN" in caplog.text

    asyncio.run(run())


def test_retry_dots_animate_without_moving_the_notice() -> None:
    sequence = render_unavailable("UTOWN")

    assert sequence.speed_ms == 250
    assert len(sequence.frames) == 8
    assert len(set(sequence.frames)) == 4
    for index in range(0, 8, 2):
        assert sequence.frames[index] == sequence.frames[index + 1]
    # Header and message remain unchanged; only the retry line animates.
    assert len({frame[: 48 * 64 * 3] for frame in sequence.frames}) == 1
