[English](en/setup-fedora.md) · **Deutsch**

# Einrichtung auf einem Fedora-Server

Supper Board läuft als Podman-Container und wird über systemd (Quadlet) gestartet – ohne Root-Rechte, mit automatischem Start nach einem Neustart.

## 1. Voraussetzungen

```bash
sudo dnf install -y podman git
```

Alles Weitere läuft als normaler Benutzer.

## 2. Herunterladen und einstellen

```bash
git clone https://github.com/pinkie87/Supper-Board.git ~/supper-board
cd ~/supper-board
cp .env.example .env
nano .env
```

Mindestens anpassen:

| Einstellung | Wofür |
|---|---|
| `SB_PASSWORD` | Passwort fürs Board. Der Browser fragt einmal danach (Benutzername beliebig). |
| `SB_PUBLIC_URL` | Adresse, unter der ihr das Board öffnet, z. B. `http://fedora.local:8080` |
| `LLM_PROVIDER` | `claude`, `ollama` oder `none`, siehe [ki.md](ki.md) |
| `HA_URL`, `HA_TOKEN`, `HA_NOTIFY` | Home Assistant, siehe [home-assistant.md](home-assistant.md) |
| `SB_SHOP_DAY` | An welchem Wochentag eingekauft wird (Standard: `sa`) |
| `SB_LANGUAGE` | `de` oder `en`: Startsprache des Boards; später im Board umschaltbar |

## 3. Bauen

```bash
podman build -t localhost/supper-board:latest -f Containerfile .
```

## 4. Als Dienst starten (Quadlet)

```bash
mkdir -p ~/.config/containers/systemd
cp deploy/supper-board.container ~/.config/containers/systemd/
systemctl --user daemon-reload
systemctl --user start supper-board
systemctl --user status supper-board
```

Die Quadlet-Datei liest die Einstellungen aus `~/supper-board/.env`. Liegt das Projekt woanders, den Pfad bei `EnvironmentFile=` anpassen.

Damit der Dienst auch ohne Anmeldung und nach einem Neustart läuft:

```bash
sudo loginctl enable-linger $USER
```

## 5. Firewall öffnen

```bash
sudo firewall-cmd --permanent --add-port=8080/tcp
sudo firewall-cmd --reload
```

Jetzt `http://<server>:8080` auf dem Handy öffnen und über das Browser-Menü **Zum Startbildschirm hinzufügen**.

> Das Board ist für das Heimnetz gedacht. Für den Zugriff von unterwegs besser ein VPN (z. B. WireGuard oder Tailscale) nutzen statt den Port ins Internet freizugeben. Wer es trotzdem freigibt: unbedingt `SB_PASSWORD` setzen und einen Reverse-Proxy mit HTTPS davorschalten (z. B. Caddy).

**Hinweis zu „Liste kopieren“:** Browser erlauben automatisches Kopieren nur über HTTPS oder auf `localhost`. Über `http://` im Heimnetz öffnet sich stattdessen ein Fenster mit der markierten Liste zum manuellen Kopieren.

## Mit compose statt Quadlet

```bash
sudo dnf install -y podman-compose
podman-compose up -d --build
```

## Aktualisieren

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

## Port 8080 schon belegt

Läuft auf dem Server schon ein anderer Dienst auf Port 8080 (z. B. die Weboberfläche von qBittorrent), startet der Container nicht. Der Dienst beendet sich gleich wieder, und systemd gibt nach einigen Versuchen auf. In `journalctl --user -u supper-board` steht dann:

```
Listen failed for HOST TCP port */8080: Address already in use
```

Wer den Port belegt, zeigt:

```bash
sudo ss -ltnp 'sport = :8080'
```

So weicht das Board auf einen anderen Port aus, hier 8081:

1. In `~/.config/containers/systemd/supper-board.container` die Zeile auf `PublishPort=8081:8080` ändern. Nur die linke Zahl (Port auf dem Server) ändert sich; die rechte ist der Port im Container und bleibt 8080.
2. In `~/supper-board/.env` die Adresse anpassen, damit die Links in den Benachrichtigungen stimmen: `SB_PUBLIC_URL=http://<Server-IP>:8081`.
3. Dienst neu laden und starten:

   ```bash
   systemctl --user daemon-reload
   systemctl --user reset-failed supper-board
   systemctl --user start supper-board
   curl http://localhost:8081/api/health
   ```

4. Falls die Firewall nur einzelne Ports durchlässt: `sudo firewall-cmd --permanent --add-port=8081/tcp && sudo firewall-cmd --reload`.

Bei compose statt Quadlet ändert man in `compose.yaml` die Zeile unter `ports` auf `"8081:8080"`.

Beim Aktualisieren die `.container`-Datei nicht erneut aus `deploy/` kopieren, sonst steht der Port wieder auf 8080.

## Datensicherung

Alle Daten liegen in einer SQLite-Datei im Podman-Volume `supper-board-data`.

```bash
# Sichern (im laufenden Betrieb möglich)
podman volume export supper-board-data > supper-board-$(date +%F).tar
# Wiederherstellen
systemctl --user stop supper-board
podman volume import supper-board-data supper-board-2026-10-06.tar
systemctl --user start supper-board
```

Den Sicherungsbefehl kann man z. B. per systemd-Timer oder cron täglich laufen lassen.
