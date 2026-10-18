from pixoo_server.display.screens.haze import parse_psi, parse_weather, psi_style, render_frame


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
