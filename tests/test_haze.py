import asyncio
import hashlib

import httpx
import pytest

from pixoo_server.display.screens.haze import (
    PSI_URL,
    WEATHER_URL,
    HazeScreen,
    parse_psi,
    parse_weather,
    psi_style,
    render_frame,
)
from pixoo_server.display.screens.unavailable import render_unavailable


def test_parses_data_gov_responses_and_renders_pixoo_frame() -> None:
    psi, timestamp = parse_psi(
        {
            "code": 0,
            "data": {
                "items": [
                    {
                        "timestamp": "2026-10-18T10:00:00+08:00",
                        "readings": {
                            "psi_twenty_four_hourly": {
                                "north": 41,
                                "south": 42,
                                "east": 43,
                                "west": 44,
                                "central": 45,
                            }
                        },
                    }
                ]
            },
        }
    )
    weather = parse_weather(
        {
            "code": 0,
            "data": {
                "records": [
                    {
                        "timestamp": "2026-10-18T10:00:00+08:00",
                        "general": {
                            "temperature": {"low": 25, "high": 32},
                            "validPeriod": {"start": "2026-10-18T06:00:00+08:00"},
                        },
                        "periods": [
                            {
                                "timePeriod": {
                                    "start": "2026-10-18T06:00:00+08:00",
                                    "end": "2026-10-18T12:00:00+08:00",
                                },
                                "regions": {
                                    region: {"text": "Partly Cloudy"}
                                    for region in ("north", "south", "east", "west", "central")
                                },
                            }
                        ],
                    }
                ]
            },
        },
        "west",
    )

    frame = render_frame(psi["west"], weather)

    assert timestamp == "2026-10-18T10:00:00+08:00"
    assert weather["forecast"] == "Partly Cloudy"
    assert len(frame) == 64 * 64 * 3
    assert len(set(frame)) > 10


def test_psi_thresholds() -> None:
    assert psi_style(50)[0] == "GOOD"
    assert psi_style(51)[0] == "MODERATE"
    assert psi_style(101)[0] == "UNHEALTHY"
    assert psi_style(301)[0] == "HAZARDOUS"


def test_render_matches_original_pixel_art() -> None:
    frame = render_frame(
        value=286,
        weather={
            "forecast": "Partly Cloudy",
            "low": 25,
            "high": 34,
            "date": "2026-10-15",
        },
        animation_frame=3,
    )

    assert hashlib.sha256(frame).hexdigest() == (
        "2215912e70223795956e86c80f09efb6ee9c3ecf032d3e5b65c10875622b9be3"
    )


def valid_payload(url: str) -> dict:
    if url == PSI_URL:
        return {
            "code": 0,
            "data": {
                "items": [
                    {
                        "timestamp": "2026-10-19T10:00:00+08:00",
                        "readings": {
                            "psi_twenty_four_hourly": dict.fromkeys(
                                ("north", "south", "east", "west", "central"), 45
                            )
                        },
                    }
                ],
            },
        }
    return {
        "code": 0,
        "data": {
            "records": [
                {
                    "timestamp": "2026-10-19T10:00:00+08:00",
                    "general": {
                        "temperature": {"low": 25, "high": 32},
                        "validPeriod": {"start": "2026-10-19T06:00:00+08:00"},
                    },
                    "periods": [
                        {
                            "timePeriod": {
                                "start": "2026-10-19T06:00:00+08:00",
                                "end": "2026-10-19T12:00:00+08:00",
                            },
                            "regions": {"west": {"text": "Partly Cloudy"}},
                        }
                    ],
                }
            ],
        },
    }


@pytest.mark.parametrize("failed_url", [PSI_URL, WEATHER_URL])
@pytest.mark.parametrize(
    "failure", ["timeout", "http_error", "invalid_json", "invalid_payload", "api_error"]
)
def test_api_failures_show_haze_fallback_and_recover(failed_url: str, failure: str, caplog) -> None:
    async def run() -> None:
        failing = True

        def handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            if failing and url == failed_url:
                if failure == "timeout":
                    raise httpx.ReadTimeout("Data API timed out", request=request)
                if failure == "http_error":
                    return httpx.Response(503)
                if failure == "invalid_json":
                    return httpx.Response(200, text="not JSON")
                if failure == "invalid_payload":
                    return httpx.Response(200, json=[])
                return httpx.Response(200, json={"code": 1, "errorMsg": "Unavailable"})
            return httpx.Response(200, json=valid_payload(url))

        screen = HazeScreen()
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            fallback = await screen.render(client, {"region": "west"})
            failing = False
            recovered = await screen.render(client, {"region": "west"})

        assert fallback == render_unavailable("HAZE")
        weather = parse_weather(valid_payload(WEATHER_URL), "west")
        assert recovered.frames == [render_frame(45, weather, phase) for phase in range(8)]
        assert "Haze data unavailable for west" in caplog.text

    asyncio.run(run())


def test_invalid_region_is_not_hidden_by_fallback() -> None:
    async def run() -> None:
        async with httpx.AsyncClient() as client:
            with pytest.raises(ValueError, match="Unknown PSI region"):
                await HazeScreen().render(client, {"region": "invalid"})

    asyncio.run(run())
