"""Versionen von Rezepten.

Bei jeder Änderung eines Rezepts wird die vorherige Fassung in ``recipe_versions``
abgelegt. So lassen sich Korrekturen der KI oder eigene Umbauten (z. B. vegetarisch)
jederzeit zurücknehmen.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from .i18n import T
from .store import Store

KEEP = 30  # Versionen pro Rezept
CONTENT = ("title", "description", "serves", "time", "oven", "ingredients", "steps", "tip", "tags", "source")
META = ("version", "versionNote", "updatedAt")


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _content(doc: dict) -> dict:
    return {k: doc.get(k) for k in CONTENT}


def snapshot(store: Store, recipe_id: str, old: dict) -> None:
    store.add("recipe_versions", {
        "recipe": recipe_id,
        "version": old.get("version") or 1,
        "note": old.get("versionNote") or "",
        "at": old.get("updatedAt") or old.get("createdAt") or _now(),
        "data": {k: v for k, v in old.items() if k not in META and k != "id"},
    })
    versions = list_versions(store, recipe_id)
    for v in versions[KEEP:]:
        store.delete("recipe_versions", v["id"])


def list_versions(store: Store, recipe_id: str) -> list[dict]:
    """Ältere Fassungen eines Rezepts, neueste zuerst."""
    found = [v for v in store.list("recipe_versions") if v.get("recipe") == recipe_id]
    return sorted(found, key=lambda v: (v.get("version") or 0, v.get("at") or ""), reverse=True)


def save(store: Store, recipe_id: str, data: dict[str, Any], note: str | None = None) -> dict:
    """Rezept speichern; eine geänderte vorherige Fassung wird als Version abgelegt."""
    data = {k: v for k, v in data.items() if k not in META and k not in ("id", "_col", "_note")}
    old = store.get("recipes", recipe_id)
    if old is None:
        data.update(version=1, versionNote=note or T("Angelegt", "Created"), updatedAt=_now())
    elif _content(old) == _content(data):
        data.update(version=old.get("version") or 1, versionNote=old.get("versionNote", ""),
                    updatedAt=old.get("updatedAt") or _now())  # nichts Inhaltliches geändert
    else:
        snapshot(store, recipe_id, old)
        data.update(version=(old.get("version") or 1) + 1, versionNote=note or T("Bearbeitet", "Edited"), updatedAt=_now())
    if old is not None and "createdAt" in old and "createdAt" not in data:
        data["createdAt"] = old["createdAt"]
    store.set("recipes", recipe_id, data)
    return data


def restore(store: Store, recipe_id: str, version_id: str) -> dict | None:
    version = store.get("recipe_versions", version_id)
    if not version or version.get("recipe") != recipe_id or store.get("recipes", recipe_id) is None:
        return None
    note = T(f"Version {version.get('version')} wiederhergestellt", f"Restored version {version.get('version')}")
    return save(store, recipe_id, dict(version.get("data") or {}), note)


def delete_all(store: Store, recipe_id: str) -> None:
    for v in list_versions(store, recipe_id):
        store.delete("recipe_versions", v["id"])
