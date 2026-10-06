"""Rezepte von Fotos (z. B. Seiten eines Kochbuchs) einlesen.

Fotos landen in ``<SB_DATA_DIR>/uploads``, je Upload ein Dokument in der Sammlung
``imports``. Ein Hintergrund-Worker gibt sie nacheinander an das Bildmodell und legt
die erkannten Rezepte im Dokument ab; das Board zeigt sie zum Prüfen an.
"""
from __future__ import annotations

import asyncio
import base64
import binascii
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from . import i18n, llm
from .config import Settings
from .i18n import T
from .planner import system_prompt
from .recipes import RECIPE_SCHEMA, clean_recipe
from .store import Store, new_id

log = logging.getLogger(__name__)

MAX_IMAGES = 20                      # pro Upload
MAX_BYTES = 8 * 1024 * 1024          # pro Bild
MIME_EXT = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
PHOTO_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"recipes": {"type": "array", "items": RECIPE_SCHEMA}},
    "required": ["recipes"],
    "additionalProperties": False,
}


class PhotoError(Exception):
    """Fehler mit einer verständlichen Meldung für das Board."""


def upload_dir(settings: Settings) -> Path:
    path = settings.data_dir / "uploads"
    path.mkdir(parents=True, exist_ok=True)
    return path


def decode_image(data_url: str) -> tuple[str, bytes]:
    m = re.fullmatch(r"data:(image/[a-z+.-]+);base64,(.+)", (data_url or "").strip(), re.S)
    if not m or m.group(1) not in MIME_EXT:
        raise PhotoError(T("Nur Fotos im Format JPEG, PNG oder WebP.", "Only JPEG, PNG or WebP photos are supported."))
    try:
        raw = base64.b64decode(m.group(2), validate=True)
    except (binascii.Error, ValueError) as e:
        raise PhotoError(T("Das Foto ist beschädigt.", "The photo is damaged.")) from e
    if len(raw) > MAX_BYTES:
        raise PhotoError(T("Ein Foto ist zu groß (höchstens 8 MB).", "A photo is too large (8 MB max)."))
    return m.group(1), raw


def create_imports(store: Store, settings: Settings, images: list[str], together: bool) -> list[str]:
    """Speichert die Fotos und legt Import-Aufträge an: ein Auftrag für alle Fotos (ein Rezept
    über mehrere Seiten) oder einer pro Foto (ganzes Buch Seite für Seite)."""
    if not images:
        raise PhotoError(T("Bitte mindestens ein Foto auswählen.", "Please choose at least one photo."))
    if len(images) > MAX_IMAGES:
        raise PhotoError(T(f"Höchstens {MAX_IMAGES} Fotos auf einmal.", f"At most {MAX_IMAGES} photos at once."))
    decoded = [decode_image(i) for i in images]  # erst alles prüfen, dann speichern
    folder = upload_dir(settings)
    groups = [decoded] if together else [[d] for d in decoded]
    ids = []
    now = datetime.now().isoformat(timespec="seconds")
    for index, group in enumerate(groups):
        doc_id = new_id()
        names = []
        for n, (mime, raw) in enumerate(group):
            name = f"{doc_id}-{n}.{MIME_EXT[mime]}"
            (folder / name).write_bytes(raw)
            names.append(name)
        # "order" hält die Reihenfolge der Fotos ein, z. B. die Seiten eines Buchs
        store.set("imports", doc_id, {"state": "waiting", "images": names, "recipes": [], "createdAt": now,
                                      "order": f"{now}#{index:03d}"})
        ids.append(doc_id)
    return ids


def delete_import(store: Store, settings: Settings, doc_id: str) -> None:
    doc = store.get("imports", doc_id) or {}
    folder = upload_dir(settings)
    for name in doc.get("images", []):
        path = (folder / name).resolve()
        if path.parent == folder.resolve():
            path.unlink(missing_ok=True)
    store.delete("imports", doc_id)


def image_path(store: Store, settings: Settings, doc_id: str, n: int) -> Path | None:
    doc = store.get("imports", doc_id) or {}
    names = doc.get("images", [])
    if not 0 <= n < len(names):
        return None
    path = upload_dir(settings) / names[n]
    return path if path.is_file() else None


def _prompt(count: int) -> str:
    pages = T("Das Foto zeigt" if count == 1 else f"Die {count} Fotos zeigen zusammen",
              "The photo shows" if count == 1 else f"The {count} photos together show")
    return T(f"""{pages} Seiten aus einem Kochbuch oder handschriftliche Rezepte.

Schreibe jedes vollständig sichtbare Rezept ab:
- Titel, Zutaten mit Mengen und alle Schritte genau so übernehmen, wie sie dort stehen. Nichts dazuerfinden, nichts weglassen.
- Mengen und Temperaturen ins Metrische und in °C umrechnen, falls nötig. Portionen, Zeit und Ofenangabe nur, wenn sie auf der Seite stehen.
- Handschriftliche Notizen zum Rezept in "tip" übernehmen.
- Unleserliche Stellen mit [?] markieren.
- Tags: 2–5 kurze Schlagworte (z. B. vegetarisch, Kuchen, Ofen).
- Geht ein Rezept über mehrere Fotos, wird es ein einziges Rezept.
- Ist kein Rezept zu erkennen (z. B. nur ein Foto oder Inhaltsverzeichnis), gib eine leere Liste zurück.""",
             f"""{pages} pages from a cookbook or handwritten recipes.

Transcribe every fully visible recipe:
- Take over the title, ingredients with quantities and all steps exactly as written. Do not invent or leave out anything.
- Convert quantities and temperatures to metric and °C if needed. Only fill in servings, time and oven if they are on the page.
- Put handwritten notes about the recipe into "tip".
- Mark unreadable parts with [?].
- Tags: 2–5 short keywords (e.g. vegetarian, cake, oven).
- If a recipe spans several photos, it is one recipe.
- If there is no recipe (e.g. only a picture or a table of contents), return an empty list.""")


async def read_photos(store: Store, settings: Settings, doc_id: str) -> None:
    doc = store.get("imports", doc_id)
    if not doc:
        return
    images = []
    folder = upload_dir(settings)
    for name in doc.get("images", []):
        ext = name.rsplit(".", 1)[-1]
        mime = next((m for m, e in MIME_EXT.items() if e == ext), "image/jpeg")
        images.append((mime, base64.b64encode((folder / name).read_bytes()).decode()))
    store.update("imports", doc_id, {"state": "working", "message": {"__delete__": True}})
    try:
        data = await llm.generate_json(settings, system_prompt(settings), _prompt(len(images)), PHOTO_SCHEMA, images=images)
    except llm.LLMError as e:
        if store.get("imports", doc_id):
            store.update("imports", doc_id, {"state": "error", "message": str(e)})
        return
    found = []
    for r in data.get("recipes") or []:
        recipe = clean_recipe(r)
        if recipe["ingredients"] or recipe["steps"]:
            recipe["source"] = T("Foto", "Photo")
            found.append(recipe)
    if store.get("imports", doc_id):  # kann inzwischen verworfen worden sein
        store.update("imports", doc_id, {"state": "done", "recipes": found})


class PhotoWorker:
    """Liest wartende Fotos nacheinander ein – auch nach einem Neustart weiter."""

    def __init__(self, store: Store, settings: Settings):
        self.store, self.settings = store, settings
        self.wake = asyncio.Event()

    async def run(self) -> None:
        for doc in self.store.list("imports"):
            if doc.get("state") == "working":  # beim Neustart unterbrochen
                self.store.update("imports", doc["id"], {"state": "waiting"})
        while True:
            waiting = sorted((d for d in self.store.list("imports") if d.get("state") == "waiting"),
                             key=lambda d: d.get("order") or d.get("createdAt", ""))
            if not waiting or not self.settings.llm_enabled:
                self.wake.clear()
                await self.wake.wait()
                continue
            i18n.use_household(self.store)
            try:
                await read_photos(self.store, self.settings, waiting[0]["id"])
            except Exception:  # noqa: BLE001 – ein kaputtes Foto darf den Worker nicht anhalten
                log.exception("Foto-Import %s fehlgeschlagen", waiting[0]["id"])
                if self.store.get("imports", waiting[0]["id"]):
                    self.store.update("imports", waiting[0]["id"], {
                        "state": "error",
                        "message": T("Unerwarteter Fehler, Details stehen im Server-Log.", "Unexpected error, see the server log for details."),
                    })
