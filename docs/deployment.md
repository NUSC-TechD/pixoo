# Raspberry Pi deployment

This runbook deploys the FastAPI server, embedded MQTT broker, and generated-GIF host with Docker Compose. It adapts the working PixooPal hotspot deployment to this Python server.

## Prerequisites

[Prerequisites](prerequisites.md) builds a fresh Pi up to this point. The Raspberry Pi then needs:

- a NetworkManager hotspot that the Pixoo can join;
- hotspot address `10.42.0.1`, or a corresponding `PIXOOPAL_HOST_IP` override;
- Docker Engine with the Compose plugin;
- Divoom DNS overrides pointing at the Pi;
- no other process listening on TCP ports `80` or `1883`.

Check the important prerequisites:

```bash
nmcli connection show --active
ip -br address show wlan0
docker --version
docker compose version
sudo ss -lntp | grep -E ':(80|1883)\b' || true
```

The expected hotspot address is:

```text
wlan0  UP  10.42.0.1/24
```

## Install the repository

```bash
git clone https://github.com/NUSC-TechD/pixoo.git ~/nusc-pixoo
cd ~/nusc-pixoo
cp .env.example .env
```

If the repository already exists, do not clone it again. Change to its directory and inspect the current state instead:

```bash
cd ~/nusc-pixoo
git status --short
git rev-parse --short HEAD
```

## Configure the server

Edit `.env` when the Pi network or ports differ from the defaults:

```dotenv
PIXOOPAL_HOST_IP=10.42.0.1
PIXOO_DEVICE_ID=12345
HTTP_PORT=80
MQTT_PORT=1883
PUBLIC_IP=80.92.211.126
PIXOO_CONFIG=/app/pixoo.toml
DATA_GOV_SG_API_KEY=
NUS_BUS_API_BASE_URL=https://bus.hewliyang.com/api/stop
```

Edit `pixoo.toml` with one block per physical Pixoo:

```toml
device_id = 12345

[[screens]]
name = "makerspace"
address = "10.42.0.8"
refresh_seconds = 60

[[screens.views]]
type = "haze"
duration_seconds = 10
region = "west"

[[screens.views]]
type = "bus_arrival"
duration_seconds = 10
stop = "UTOWN"
```

The `address` must be reachable from the Pi. A DHCP reservation is preferable so it does not change after a reboot.

## Configure DNS interception

The Pixoo firmware must resolve the Divoom cloud hostnames to the Raspberry Pi:

```ini
address=/appin.divoom-gz.com/10.42.0.1
address=/app.divoom-gz.com/10.42.0.1
```

Keep these entries in the NetworkManager-managed dnsmasq configuration used by the hotspot. Do not run a second standalone dnsmasq service on the same interface.

Restart the hotspot after changing its DNS configuration:

```bash
sudo nmcli connection down PixooLocal
sudo nmcli connection up PixooLocal
```

This disconnects every hotspot client. Power-cycle the Pixoo after the server is running.

## Start the server

Stop the old PixooPal or minimal-emulator container first because only one process can own ports `80` and `1883`:

```bash
docker ps --format 'table {{.Names}}\t{{.Ports}}'
```

Then validate and start this deployment:

```bash
cd ~/nusc-pixoo
docker compose config
docker compose up -d --build --force-recreate
docker compose ps
docker compose logs --timestamps --no-color --since 5m
```

Power-cycle the Pixoo. A successful startup normally shows requests to `/Test/GetIP` and `/Device/InitV2`, followed by an MQTT connection.

## Verify the deployment

Confirm the server owns both ports:

```bash
sudo ss -lntp | grep -E ':(80|1883)\b'
```

Check process liveness and MQTT state:

```bash
curl -i http://10.42.0.1/health/live
curl -i http://10.42.0.1/health
```

`/health/live` should return HTTP `200`. `/health` returns HTTP `200` while a Pixoo MQTT session is active and HTTP `503` before the device connects or after it becomes inactive.

Inspect configured displays and force a refresh:

```bash
curl -sS http://10.42.0.1/api/screens
curl -i -X POST http://10.42.0.1/api/screens/makerspace/refresh
curl -o /tmp/makerspace.gif http://10.42.0.1/api/screens/makerspace/animation.gif
file /tmp/makerspace.gif
```

Use the exact Pixoo `name` from `pixoo.toml` in the URL. The GIF endpoint returns `404` until the first successful render.

## Update the deployment

Review local changes before pulling so deployment-specific edits are not overwritten:

```bash
cd ~/nusc-pixoo
git status --short
git pull --ff-only
docker compose up -d --build --force-recreate
docker compose ps
docker compose logs --timestamps --no-color --since 5m
```

Power-cycle the Pixoo only when it does not reconnect automatically.

## Stop or restart

```bash
cd ~/nusc-pixoo
docker compose restart
docker compose down
```

`docker compose down` stops cloud emulation, MQTT, API access, and hosted GIF delivery.
