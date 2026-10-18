# Pixoo debugging runbook

This runbook assumes:

- hotspot connection `PixooLocal`;
- Raspberry Pi address `10.42.0.1`;
- example Pixoo address `10.42.0.8`;
- project directory `~/nusc-pixoo`.

Replace the addresses and physical interface when your deployment differs.

## Quick health check

```bash
nmcli connection show --active
iw dev wlan0 info | grep -E 'type|channel'
ip -br address show wlan0
ip route
ip neigh show dev wlan0
sudo iw dev wlan0 station dump
cd ~/nusc-pixoo
docker compose ps
curl -i http://10.42.0.1/health/live
curl -i http://10.42.0.1/health
```

A healthy hotspot should show `PixooLocal`, wireless mode `AP`, and `10.42.0.1/24` on `wlan0`.

## Hotspot control

Show the hotspot configuration:

```bash
nmcli -f connection.id,802-11-wireless.mode,802-11-wireless.band,802-11-wireless.channel,ipv4.method,ipv4.addresses,ipv4.shared-dhcp-range connection show PixooLocal
```

Restart only the hotspot:

```bash
sudo nmcli connection down PixooLocal
sudo nmcli connection up PixooLocal
```

Restart the Wi-Fi radio and hotspot when the interface itself is unhealthy:

```bash
sudo nmcli radio wifi off
sleep 3
sudo nmcli radio wifi on
sudo nmcli connection up PixooLocal
```

Restarting the hotspot disconnects all clients. Power-cycle the Pixoo afterward and allow it time to reconnect.

## Wi-Fi association and DHCP

Show associated clients and link quality:

```bash
sudo iw dev wlan0 station dump
sudo iw dev wlan0 station dump | grep -E 'Station|inactive|signal:|rx bytes|tx bytes|rx packets|tx packets|rx bitrate|tx bitrate|tx retries|tx failed|authorized|authenticated|associated'
```

Healthy clients report:

```text
authorized: yes
authenticated: yes
associated: yes
```

Inspect recent DHCP activity:

```bash
sudo journalctl -u NetworkManager --since '-10 minutes' --no-pager | grep -Ei 'DHCPDISCOVER|DHCPOFFER|DHCPREQUEST|DHCPACK'
```

A complete lease exchange is `DHCPDISCOVER`, `DHCPOFFER`, `DHCPREQUEST`, then `DHCPACK`.

Inspect and repair neighbour discovery:

```bash
ip neigh show dev wlan0
sudo ip neigh del 10.42.0.8 dev wlan0 2>/dev/null || true
ping -c 3 10.42.0.8
```

`FAILED` means the Pi sent ARP requests but the Pixoo did not answer. Check whether the device is still associated before assuming DHCP failed.

## DNS interception

Confirm both firmware hostnames resolve to the Pi:

```bash
dig @10.42.0.1 appin.divoom-gz.com +short
dig @10.42.0.1 app.divoom-gz.com +short
```

Both should return:

```text
10.42.0.1
```

Inspect DNS and DHCP listeners:

```bash
ps -ef | grep '[d]nsmasq'
sudo ss -luntp | grep -E ':(53|67)\b'
systemctl is-enabled dnsmasq
systemctl is-active dnsmasq
```

When NetworkManager manages the shared hotspot, the standalone `dnsmasq.service` should normally remain disabled.

## Container and server logs

```bash
cd ~/nusc-pixoo
docker compose ps
docker compose logs --timestamps --no-color --since 10m
docker compose logs --timestamps --no-color --tail=0 -f
```

Stop following logs with `Ctrl+C`; the container continues running.

Rebuild or restart:

```bash
docker compose up -d --build --force-recreate
docker compose restart
```

Check port ownership when the container fails to start:

```bash
sudo ss -lntp | grep -E ':(80|1883)\b'
docker ps --format 'table {{.Names}}\t{{.Ports}}'
```

## Cloud emulator and MQTT

Check the current session state:

```bash
curl -i http://10.42.0.1/health
watch -n 5 'curl -s http://10.42.0.1/health'
```

The JSON reports:

- whether the shared MQTT identity is connected;
- connection and inactivity durations;
- the last firmware command;
- disconnect count;
- cloud bootstrap count.

An HTTP `503` means no currently healthy MQTT session. Check DNS interception, server ports, and the MQTT packet capture before investigating display rendering.

## Display pipeline

List configured Pixoo devices and their most recent update state:

```bash
curl -sS http://10.42.0.1/api/screens
```

Force a render and delivery attempt:

```bash
curl -i -X POST http://10.42.0.1/api/screens/makerspace/refresh
```

Download the exact GIF offered to the Pixoo:

```bash
curl -i http://10.42.0.1/api/screens/makerspace/animation.gif
curl -o /tmp/makerspace.gif http://10.42.0.1/api/screens/makerspace/animation.gif
file /tmp/makerspace.gif
```

Use the exact configured name. Interpret common responses as follows:

| Response | Meaning |
| --- | --- |
| GIF endpoint `404` | No successful render has been stored yet |
| Refresh `404` | The Pixoo name is not configured |
| Refresh `409` | Scheduler is stopped or that Pixoo is already updating |
| Refresh `502` | Data fetching, rendering, Pixoo delivery, or device response failed |

## Direct Pixoo HTTP API

Read the device configuration directly:

```bash
curl -sS --connect-timeout 5 --max-time 15 \
  -H 'Content-Type: application/json' \
  -H 'Connection: close' \
  -d '{"Command":"Channel/GetAllConf"}' \
  http://10.42.0.8/post
```

Measure device latency:

```bash
curl -sS --connect-timeout 10 --max-time 30 \
  -o /tmp/pixoo-response.json \
  -w 'connect=%{time_connect}s start-transfer=%{time_starttransfer}s total=%{time_total}s\n' \
  -H 'Content-Type: application/json' \
  -H 'Connection: close' \
  -d '{"Command":"Channel/GetAllConf"}' \
  http://10.42.0.8/post

cat /tmp/pixoo-response.json
```

Change brightness as an isolated device test:

```bash
curl -sS \
  -H 'Content-Type: application/json' \
  -d '{"Command":"Channel/SetBrightness","Brightness":50}' \
  http://10.42.0.8/post
```

If these commands fail, the problem is between the Pi and Pixoo rather than in rendering or data.gov.sg.

## Packet captures

Capture DHCP and ARP traffic for 60 seconds:

```bash
sudo timeout 60 tcpdump -ni wlan0 -e -tttt -vv \
  'host 10.42.0.8 and (arp or udp port 67 or udp port 68)' \
  2>&1 | tee ~/pixoo-dhcp-arp.txt
```

Capture MQTT traffic for 120 seconds:

```bash
sudo timeout 120 tcpdump -ni wlan0 -s0 -tttt -vvv -X \
  'host 10.42.0.8 and tcp port 1883' \
  2>&1 | tee ~/pixoo-mqtt-120s.txt
```

Capture direct Pixoo HTTP traffic for 30 seconds:

```bash
sudo timeout 30 tcpdump -ni wlan0 -s0 -tttt -vvv -A \
  'host 10.42.0.8 and tcp port 80' \
  2>&1 | tee ~/pixoo-http-30s.txt
```

Start the relevant capture first, then power-cycle the Pixoo or trigger a manual refresh.

## Raspberry Pi power and kernel errors

Check current and historical throttling flags:

```bash
vcgencmd get_throttled
```

Healthy output is:

```text
throttled=0x0
```

Check recent power and Wi-Fi errors:

```bash
sudo journalctl -k --since '-15 minutes' --no-pager | grep -Ei 'under-voltage|voltage|brcmfmac|wlan0|firmware|error'
```

## Symptom guide

| Symptom | Most useful checks |
| --- | --- |
| Pixoo stuck near 60% | Hotspot state, association, DHCP logs, Pi power |
| Pixoo stuck near 80% | HTTP/MQTT ports, server logs, MQTT capture |
| `ip neigh` reports `FAILED` | Association state, DHCP logs, ARP capture |
| Direct Pixoo HTTP times out | Neighbour table, station state, HTTP capture |
| `/health` remains `503` | DNS overrides, MQTT listener, MQTT capture |
| GIF endpoint returns `404` | Scheduler logs, data.gov.sg response, configured view |
| Manual refresh returns `502` | Container traceback, Pixoo reachability, direct HTTP test |
| Container cannot bind a port | Port ownership and old PixooPal containers |
| Pi restarts or Wi-Fi is erratic | Throttling flags and kernel logs |
