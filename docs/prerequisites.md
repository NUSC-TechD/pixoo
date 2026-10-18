# Raspberry Pi prerequisites

Prepare a fresh Raspberry Pi so [deployment](deployment.md) can start. This covers the OS image, the Pixoo hotspot, and Divoom DNS interception.

The Pi needs two networks:

- Ethernet is the internet uplink. The server fetches data.gov.sg and pulls container images through it.
- `wlan0` is only the hotspot. The Pixoo joins this network.

Use the current NUSC defaults unless your site differs:

- hotspot name: `PixooLocal`
- hotspot address: `10.42.0.1/24`
- example Pixoo address: `10.42.0.8`
- Wi-Fi country: `SG`

## Flash Raspberry Pi OS

On another computer, install [Raspberry Pi Imager](https://www.raspberrypi.com/software/) 2.x and write the card:

1. Choose the Pi model.
2. Choose **Raspberry Pi OS (64-bit) Lite**. A desktop is not used.
3. Choose the microSD card.
4. Open OS customisation and set:
   - hostname `nusc-pixoo`;
   - a username and password;
   - SSH, preferably with your public key;
   - time zone `Asia/Singapore`;
   - Wi-Fi country `SG`.
5. Leave the Wi-Fi network blank. A client profile on `wlan0` competes with the hotspot.
6. Write the card, put it in the Pi, connect Ethernet, and power on.

Imager 1.x cannot apply these settings to current Raspberry Pi OS images.

## First boot

Wait a few minutes, then connect:

```bash
ssh <user>@nusc-pixoo.local
```

If the hostname does not resolve, use the Ethernet address from the router.

Set the Wi-Fi country if Imager did not, then update:

```bash
sudo raspi-config nonint do_wifi_country SG
sudo apt update
sudo apt full-upgrade -y
sudo apt install -y git dnsmasq-base bind9-dnsutils docker.io docker-compose-v2
sudo usermod -aG docker "$USER"
sudo reboot
```

Log in again so the `docker` group applies. `dnsmasq-base` supplies the binary NetworkManager uses. Do not install or enable the standalone `dnsmasq` service.

Confirm Ethernet has an address and outbound internet works:

```bash
ip -br address show eth0
ping -c 3 data.gov.sg
```

## Create the hotspot

Replace the passphrase. It must be 8–63 characters.

```bash
sudo nmcli connection add \
  type wifi \
  ifname wlan0 \
  con-name PixooLocal \
  autoconnect yes \
  ssid PixooLocal \
  802-11-wireless.mode ap \
  802-11-wireless.band bg \
  802-11-wireless.channel 6 \
  802-11-wireless.powersave 2 \
  ipv4.method shared \
  ipv4.addresses 10.42.0.1/24 \
  ipv4.shared-dhcp-range '10.42.0.2,10.42.0.254,24h' \
  ipv6.method disabled \
  wifi-sec.key-mgmt wpa-psk \
  wifi-sec.psk 'replace-with-a-passphrase'

sudo nmcli connection up PixooLocal
```

The Pixoo 64 is 2.4 GHz only, so the band stays `bg`. Shared mode makes NetworkManager the DHCP server and DNS forwarder for `10.42.0.0/24`, and NATs client traffic out through Ethernet. Power save is disabled because the onboard radio otherwise drops associated clients.

If a Wi-Fi client profile still exists, stop it from taking `wlan0`:

```bash
nmcli -t -f NAME,TYPE connection show
sudo nmcli connection modify '<client-profile>' connection.autoconnect no
sudo nmcli connection up PixooLocal
```

Check the access point:

```bash
nmcli connection show --active
ip -br address show wlan0
iw dev wlan0 info | grep -E 'type|ssid|channel'
```

Expected:

```text
wlan0  UP  10.42.0.1/24
type AP
ssid PixooLocal
channel 6
```

Join the Pixoo to `PixooLocal` with the Divoom app. The phone has to be on that hotspot during device Wi-Fi setup. Other names still resolve through the Pi; only the Divoom names in the next section are overridden.

## Intercept Divoom DNS

The firmware must resolve its cloud hosts to the Pi. Create the NetworkManager dnsmasq snippet:

```bash
sudo mkdir -p /etc/NetworkManager/dnsmasq-shared.d
sudo tee /etc/NetworkManager/dnsmasq-shared.d/divoom.conf >/dev/null <<'EOF'
address=/appin.divoom-gz.com/10.42.0.1
address=/app.divoom-gz.com/10.42.0.1
EOF
sudo nmcli connection down PixooLocal
sudo nmcli connection up PixooLocal
```

NetworkManager reads `dnsmasq-shared.d` only for shared connections. Restarting the hotspot disconnects every client.

Confirm the standalone service is not owning DNS, then query the hotspot resolver:

```bash
systemctl is-enabled dnsmasq || true
systemctl is-active dnsmasq || true
dig @10.42.0.1 appin.divoom-gz.com +short
dig @10.42.0.1 app.divoom-gz.com +short
ps -ef | grep '[d]nsmasq'
```

Both `dig` commands should print `10.42.0.1`. The `dnsmasq` service should be disabled, inactive, or not installed. The running process should include `--conf-dir=/etc/NetworkManager/dnsmasq-shared.d`.

## Reserve a Pixoo address

DHCP may give the Pixoo a different address after a reboot. Pin it before writing `pixoo.toml`.

After the Pixoo associates, read its MAC:

```bash
ip neigh show dev wlan0
```

Add one `dhcp-host` line per device to the same snippet. `10.42.0.8` is the example address used in the other runbooks:

```bash
sudo tee -a /etc/NetworkManager/dnsmasq-shared.d/divoom.conf >/dev/null <<'EOF'
dhcp-host=aa:bb:cc:dd:ee:ff,10.42.0.8
EOF
sudo nmcli connection down PixooLocal
sudo nmcli connection up PixooLocal
```

Use the MAC from `ip neigh`, with lowercase hex and colons. Power-cycle the Pixoo and confirm the lease:

```bash
ip neigh show dev wlan0
```

## Check Docker

```bash
docker --version
docker compose version
```

If those commands say permission denied, log out of SSH and back in so the `docker` group membership applies.

## Next

Continue with [deployment](deployment.md). The preflight there should show `PixooLocal`, `10.42.0.1/24` on `wlan0`, and both Divoom names resolving to the Pi.
