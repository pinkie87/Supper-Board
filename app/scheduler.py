"""Zeitplan: wöchentlicher Planentwurf, Einkaufsliste und tägliche Erinnerungen."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

from . import i18n, notify, planner
from .config import Settings
from .i18n import T
from .store import Store

log = logging.getLogger(__name__)


def _thaw_message(store: Store, settings: Settings) -> str | None:
    tomorrow = (planner.today(settings) + timedelta(days=1)).isoformat()
    for m in store.list("meals") + store.list("draft"):
        if m.get("date") == tomorrow and m.get("thaw") and not m.get("thawDone"):
            return T(f"Vor dem Schlafengehen: {m['thaw']} aus dem Gefrierfach in den Kühlschrank legen – für morgen: {m['title']}.",
                     f"Before bed: move {m['thaw']} from the freezer to the fridge – for tomorrow: {m['title']}.")
    return None


def _dinner_message(store: Store, settings: Settings) -> str | None:
    t = planner.today(settings).isoformat()
    for m in store.list("meals"):
        if m.get("date") == t:
            if m.get("kind") == "cook" and m.get("recipe"):
                time = (m.get("recipe") or {}).get("time")
                return T(f"Heute wird gekocht: {m['title']}", f"Cooking tonight: {m['title']}") + (f" ({time})" if time else "") + "."
            return T(f"Heute Abend: {m['title']}.", f"Tonight: {m['title']}.")
    return None


async def tick(store: Store, settings: Settings, now: datetime) -> None:
    """Wird einmal pro Minute aufgerufen."""
    i18n.use_household(store)
    hm = (now.hour, now.minute)
    wd = now.weekday()
    if hm == (0, 5):
        planner.housekeeping(store, settings)
    if wd == settings.draft_weekday and hm == settings.draft_time:
        await planner.run_job(store, settings, "draft", lambda: planner.draft_plan(store, settings))
    if wd == settings.list_weekday and hm == settings.list_time:
        await planner.run_job(store, settings, "list", lambda: planner.finalize_list(store, settings))
    if hm == settings.thaw_time:
        msg = _thaw_message(store, settings)
        if msg:
            await notify.send(settings, T("Auftauen nicht vergessen", "Don't forget to thaw"), msg)
    if hm == settings.dinner_time:
        msg = _dinner_message(store, settings)
        if msg:
            await notify.send(settings, T("Abendessen", "Dinner"), msg)


async def run(store: Store, settings: Settings) -> None:
    planner.housekeeping(store, settings)
    last = None
    while True:
        now = datetime.now(settings.timezone).replace(second=0, microsecond=0)
        if now != last:
            last = now
            try:
                await tick(store, settings, now)
            except Exception:  # noqa: BLE001 – der Zeitplan darf nie stehen bleiben
                log.exception("Fehler im Zeitplan")
        await asyncio.sleep(20)
