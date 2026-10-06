"""Benachrichtigungen über Home Assistant (notify-Dienste, z. B. die Companion-App)."""
from __future__ import annotations

import logging

import httpx

from .config import Settings

log = logging.getLogger(__name__)


def enabled(settings: Settings) -> bool:
    return bool(settings.ha_url and settings.ha_token and settings.ha_notify)


async def send(settings: Settings, title: str, message: str) -> bool:
    """Schickt eine Nachricht an alle in HA_NOTIFY genannten Dienste. Fehler werden nur geloggt."""
    if not enabled(settings):
        log.info("Benachrichtigung (Home Assistant nicht eingerichtet): %s – %s", title, message)
        return False
    data: dict = {"title": title, "message": message}
    if settings.public_url:
        # clickAction: Android-App, url: iOS-App – öffnet beim Antippen das Board.
        data["data"] = {"clickAction": settings.public_url, "url": settings.public_url}
    ok = True
    async with httpx.AsyncClient(timeout=15.0) as client:
        for service in settings.ha_notify:
            name = service.removeprefix("notify.")
            try:
                r = await client.post(
                    f"{settings.ha_url}/api/services/notify/{name}",
                    headers={"Authorization": f"Bearer {settings.ha_token}"},
                    json=data,
                )
                if r.status_code >= 300:
                    ok = False
                    log.warning("Home Assistant notify.%s: Fehler %s %s", name, r.status_code, r.text[:200])
            except httpx.HTTPError as e:
                ok = False
                log.warning("Home Assistant nicht erreichbar (%s): %s", name, e)
    return ok
