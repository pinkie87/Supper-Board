"""Mehrere Rezept-Links auf einmal importieren.

Jeder Link wird ein Auftrag in ``imports`` (``kind: "link"``). Der Hintergrund-Worker
holt die Seiten nacheinander mit einer Pause dazwischen, damit die Rezeptseite nicht
belastet wird. Die Rezepte landen zum Prüfen im Board; Bilder werden nicht übernommen.
"""
from __future__ import annotations

import json
from datetime import datetime
from urllib.parse import urlparse

from . import llm, planner, recipes
from .config import Settings
from .htmlrecipe import extract_recipe
from .i18n import T
from .store import Store, new_id
from .units import UnitOptions, convert_text

MAX_LINKS = 300
DELAY = 4.0  # Sekunden Pause zwischen zwei Abrufen


class LinkError(Exception):
    """Fehler mit einer verständlichen Meldung für das Board."""


def _norm(url: str) -> str:
    return url.strip().split("#")[0].rstrip("/")


def create_link_imports(store: Store, urls: list[str]) -> dict:
    """Legt für jeden neuen Link einen Auftrag an. Bekannte Links (schon in der Datenbank
    oder in der Warteschlange) werden übersprungen."""
    clean: list[str] = []
    for u in urls:
        u = str(u or "").strip()
        if not u:
            continue
        p = urlparse(u)
        if p.scheme not in ("http", "https") or not p.netloc:
            raise LinkError(T(f"Kein gültiger Link: {u[:80]}", f"Not a valid link: {u[:80]}"))
        if _norm(u) not in {_norm(c) for c in clean}:
            clean.append(u)
    if not clean:
        raise LinkError(T("Bitte mindestens einen Link angeben.", "Please enter at least one link."))
    if len(clean) > MAX_LINKS:
        raise LinkError(T(f"Höchstens {MAX_LINKS} Links auf einmal.", f"At most {MAX_LINKS} links at once."))
    known = {_norm(r.get("source") or "") for r in store.list("recipes")}
    known |= {_norm(i.get("url") or "") for i in store.list("imports") if i.get("kind") == "link"}
    now = datetime.now().isoformat(timespec="seconds")
    ids, skipped = [], 0
    for index, url in enumerate(clean):
        if _norm(url) in known:
            skipped += 1
            continue
        doc_id = new_id()
        store.set("imports", doc_id, {"kind": "link", "url": url, "state": "waiting", "recipes": [], "images": [],
                                      "createdAt": now, "order": f"{now}#{index:03d}"})
        ids.append(doc_id)
    return {"ids": ids, "skipped": skipped}


async def read_link(store: Store, settings: Settings, doc_id: str) -> None:
    doc = store.get("imports", doc_id)
    if not doc:
        return
    url = doc["url"]
    store.update("imports", doc_id, {"state": "working", "message": {"__delete__": True}})
    try:
        page = await recipes.fetch_page(url)
        recipe = extract_recipe(page)
        if recipe and recipes.needs_metric(recipe):
            if settings.llm_enabled:
                recipe = await planner.recipe_from_text(settings, json.dumps(recipe, ensure_ascii=False))
            else:
                opts = UnitOptions(origin="us")
                recipe["ingredients"] = [convert_text(i, opts) for i in recipe["ingredients"]]
                recipe["steps"] = [convert_text(s, opts) for s in recipe["steps"]]
                recipe["oven"] = convert_text(recipe.get("oven", ""), opts)
        if not recipe and settings.llm_enabled:
            recipe = await planner.recipe_from_text(settings, recipes.page_text(page))
    except recipes.ImportError_ as e:
        _fail(store, doc_id, str(e))
        return
    except llm.LLMRateLimited:
        if store.get("imports", doc_id):
            store.update("imports", doc_id, {"state": "waiting"})
        raise
    except llm.LLMError as e:
        _fail(store, doc_id, str(e))
        return
    if not recipe or not (recipe.get("ingredients") or recipe.get("steps")):
        _fail(store, doc_id, T("Auf dieser Seite wurde kein Rezept gefunden.", "No recipe was found on this page.")
              + ("" if settings.llm_enabled else T(" Mit eingerichteter KI klappt es eventuell.", " It may work with an AI set up.")))
        return
    recipe = {k: v for k, v in recipe.items() if k != "image"}
    recipe["source"] = url
    if store.get("imports", doc_id):
        store.update("imports", doc_id, {"state": "done", "recipes": [recipe], "title": recipe.get("title", ""),
                                         "message": {"__delete__": True}})


def _fail(store: Store, doc_id: str, message: str) -> None:
    if store.get("imports", doc_id):
        store.update("imports", doc_id, {"state": "error", "message": message})
