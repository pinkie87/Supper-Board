**English** · [Deutsch](../einrichtung-fedora.md)

# Setup on a Fedora server

Supper Board runs as a Podman container and is started through systemd (Quadlet): no root privileges, and it comes back up automatically after a reboot.

## 1. Prerequisites

```bash
sudo dnf install -y podman git
```

Everything else runs as a regular user.

## 2. Download and configure

```bash
git clone https://github.com/pinkie87/Supper-Board.git ~/supper-board
cd ~/supper-board
cp .env.example .env
nano .env
```

Adjust at least:

| Setting | Purpose |
|---|---|
| `SB_PASSWORD` | Password for the board. The browser asks once (any user name works). |
| `SB_PUBLIC_URL` | Address you open the board at, e.g. `http://fedora.local:8080` |
| `LLM_PROVIDER` | `claude`, `ollama` or `none`, see [ai.md](ai.md) |
| `HA_URL`, `HA_TOKEN`, `HA_NOTIFY` | Home Assistant, see [home-assistant.md](home-assistant.md) |
| `SB_SHOP_DAY` | Weekday you go shopping (default: `sa`) |
| `SB_LANGUAGE` | `de` or `en`: language the board starts in; can be switched in the board later |

Weekdays in `.env` use German abbreviations: `mo di mi do fr sa so` (Monday to Sunday).

## 3. Build

```bash
podman build -t localhost/supper-board:latest -f Containerfile .
```

## 4. Start as a service (Quadlet)

```bash
mkdir -p ~/.config/containers/systemd
cp deploy/supper-board.container ~/.config/containers/systemd/
systemctl --user daemon-reload
systemctl --user start supper-board
systemctl --user status supper-board
```

The Quadlet file reads its settings from `~/supper-board/.env`. If the project lives elsewhere, adjust the path in `EnvironmentFile=`.

To keep the service running without a login session and after a reboot:

```bash
sudo loginctl enable-linger $USER
```

## 5. Open the firewall

```bash
sudo firewall-cmd --permanent --add-port=8080/tcp
sudo firewall-cmd --reload
```

Now open `http://<server>:8080` on your phone and use the browser menu to **Add to Home Screen**.

> The board is meant for your home network. For access on the go, use a VPN (e.g. WireGuard or Tailscale) rather than exposing the port to the internet. If you do expose it: always set `SB_PASSWORD` and put a reverse proxy with HTTPS in front (e.g. Caddy).

**About "copy list":** browsers only allow automatic copying over HTTPS or on `localhost`. Over `http://` on your home network, a window with the selected list opens instead so you can copy it by hand.

## Using compose instead of Quadlet

```bash
sudo dnf install -y podman-compose
podman-compose up -d --build
```

## Updating

```bash
cd ~/supper-board
git pull
podman build -t localhost/supper-board:latest -f Containerfile .
systemctl --user restart supper-board
```

## Logs

```bash
journalctl --user -u supper-board -f
```

## Port 8080 already in use

If another service on the server already uses port 8080 (for example the qBittorrent web UI), the container doesn't start. The service exits right away and systemd gives up after a few attempts. `journalctl --user -u supper-board` then shows:

```
Listen failed for HOST TCP port */8080: Address already in use
```

To see what's using the port:

```bash
sudo ss -ltnp 'sport = :8080'
```

To move the board to another port, here 8081:

1. In `~/.config/containers/systemd/supper-board.container`, change the line to `PublishPort=8081:8080`. Only the left number (the port on the server) changes; the right one is the port inside the container and stays 8080.
2. In `~/supper-board/.env`, update the address so links in notifications are correct: `SB_PUBLIC_URL=http://<server-ip>:8081`.
3. Reload and start the service:

   ```bash
   systemctl --user daemon-reload
   systemctl --user reset-failed supper-board
   systemctl --user start supper-board
   curl http://localhost:8081/api/health
   ```

4. If your firewall only allows specific ports: `sudo firewall-cmd --permanent --add-port=8081/tcp && sudo firewall-cmd --reload`.

With compose instead of Quadlet, change the line under `ports` in `compose.yaml` to `"8081:8080"`.

When updating, don't copy the `.container` file from `deploy/` again, or the port goes back to 8080.

## Backups

All data lives in one SQLite file inside the Podman volume `supper-board-data`.

```bash
# Back up (works while running)
podman volume export supper-board-data > supper-board-$(date +%F).tar
# Restore
systemctl --user stop supper-board
podman volume import supper-board-data supper-board-2026-10-06.tar
systemctl --user start supper-board
```

You can run the backup command daily, e.g. with a systemd timer or cron.
