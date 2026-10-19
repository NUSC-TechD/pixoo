# NUSC Pixoo server

Local-first Python server for managing Divoom Pixoo 64 displays across NUSC. It combines:

- the minimal local first Divoom cloud and MQTT server (inspired by [Drun555/PixooPal](https://github.com/Drun555/PixooPal));
- the Singapore PSI/weather display;
- live UTown shuttle arrivals with the next two buses per route;
- configurable multi-screen playlists and one-minute refreshes;
- FastAPI status and manual-refresh endpoints;
- reproducible `uv` dependencies, Docker Compose, and tests.

The project does not include the original PixooPal web UI or community clockface system.

## Architecture

```text
Pixoo firmware -- HTTP :80 --> FastAPI cloud bootstrap
               -- MQTT :1883 -> Pixoo-specific MQTT broker

data.gov.sg ---------> haze screen -------+
NUS bus API ---------> bus-arrival screen +--> playlist --> hosted GIF --> Pixoo
```

The source tree follows those responsibilities directly:

```text
src/pixoo_server/
├── api/                # Operator-facing status and refresh endpoints
├── config/             # TOML schemas and environment settings
├── cloud_emulator/     # Divoom bootstrap routes, responses, and device state
├── mqtt/               # MQTT broker lifecycle and packet encoding/decoding
├── display/            # Pixoo delivery client, playlists, and scheduler
│   └── screens/        # One module per information screen
└── main.py             # FastAPI composition root and server entry point
```

The MQTT implementation deliberately supports the firmware subset rather than pretending to be a general broker. It handles connect/authentication, subscriptions, QoS 1/2 acknowledgements, ping, heartbeats, captured startup response shapes, malformed Pixoo publish framing, and whole-packet writes.

## Configure displays

Edit `pixoo.toml`. Cloud bootstrap uses one shared device ID; each physical screen
only needs a unique `name` and a network `address`:

```toml
device_id = 12345

[[screens]]
name = "makerspace"
address = "10.42.0.8"
refresh_seconds = 60

[[screens.views]]
type = "haze"
duration_seconds = 5
region = "west"

[[screens.views]]
type = "bus_arrival"
duration_seconds = 5
stop = "UTOWN"
```

Add another `[[screens]]` block to drive another Pixoo independently. A physical screen may contain multiple `[[screens.views]]` entries. Each content screen is shown for 10 seconds by default, or for its configured `duration_seconds`, before the GIF advances to the next one. The Pixoo loops the complete GIF automatically and indefinitely.

If the bus, PSI, or weather API fails, the affected view shows `LIVE DATA UNAVAILABLE`
with animated `RETRYING...` dots while other views continue refreshing. The server
logs the failure and retries at the next playlist refresh; successful responses
restore the normal content.

The NUS bus proxy is a community-run service, so bus requests are throttled in-process:
each stop is fetched at most once per minute no matter how often screens refresh (including
manual refreshes), responses are cached for at least that minute (longer if the server sends
`Cache-Control: max-age`) and revalidated with `ETag`/`Last-Modified`, and failures back off
exponentially with jitter up to 30 minutes, honouring `Retry-After`. Requests identify
themselves as `NUSC-Pixoo-BusBoard/0.1 (+https://github.com/NUSC-TechD/pixoo; ...)`.

Environment variables:

| Variable | Default | Purpose |
| --- | --- | --- |
| `PIXOOPAL_HOST_IP` | `10.42.0.1` | MQTT address advertised to firmware |
| `PIXOO_DEVICE_ID` | `12345` | Shared cloud and MQTT identity advertised to all firmware |
| `HTTP_PORT` | `80` | FastAPI port |
| `MQTT_PORT` | `1883` | MQTT port advertised and served |
| `PUBLIC_IP` | `80.92.211.126` | Harmless bootstrap response value |
| `PIXOO_CONFIG` | `pixoo.toml` | TOML configuration path |
| `DATA_GOV_SG_API_KEY` | empty | Optional higher-rate-limit API key |
| `NUS_BUS_API_BASE_URL` | `https://bus.hewliyang.com/api/stop` | Configurable NUS bus timing proxy |

Configuration is validated by Pydantic. Explicit constructor values used by tests have the
highest priority, followed by environment variables, `.env`, `pixoo.toml`, and built-in defaults.
Invalid ports, duplicate screen names, and malformed screen or view entries fail at startup
with a structured validation error.

## Run locally

```bash
uv sync
uv run python -m pixoo_server.main
```

Ports 80 and 1883 may require elevated privileges or port redirection on a development machine. For API-only development, temporarily set `HTTP_PORT` and `MQTT_PORT` to unprivileged ports.

Useful endpoints:

- `GET /health/live` — process liveness;
- `GET /health` — MQTT connection state (`503` until a Pixoo is online);
- `GET /api/screens` — display update state;
- `GET /api/screens/{name}/animation.gif` — latest generated animation for a screen;
- `POST /api/screens/{name}/refresh` — render, publish, and play a fresh GIF;
- `/docs` — generated FastAPI API documentation.

## Operations documentation

- [Raspberry Pi prerequisites](docs/prerequisites.md)
- [Raspberry Pi deployment](docs/deployment.md)
- [Debugging runbook](docs/debugging.md)

## Run on the Raspberry Pi

The known deployment uses host networking because the intercepted Divoom DNS names resolve to the Pi itself and the firmware expects ports 80/1883.

```bash
cp .env.example .env
# Edit pixoo.toml and .env.
docker compose up -d --build
docker compose logs -f
```

Keep the NetworkManager dnsmasq overrides pointing at the Pi hotspot address:

```ini
address=/appin.divoom-gz.com/10.42.0.1
address=/app.divoom-gz.com/10.42.0.1
```

Only one service can own ports 80 and 1883, so stop the old PixooPal/minimal-emulator container first. Power-cycle the Pixoo after the new service is running.

## Development

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
docker compose config
docker build -t nusc-pixoo:test .
```

To add a new kind of information screen, such as weather, transport, or events:

1. Add a class under `display/screens/`, following the `HazeScreen.render(client, options) -> FrameSequence` contract.
2. Add its type name to `ViewConfig.type`.
3. Create it in the `DisplayScheduler._screen_types` registry.
4. Add parsing, screen-output, and playlist tests.
5. Add the new view to one or more physical screen blocks in `pixoo.toml`.

Network calls and physical uploads are kept out of rendering functions, which makes new screens testable without hardware.
