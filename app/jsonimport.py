"""Rezepte aus einer JSON-Datei übernehmen, z. B. aus einem eigenen Scraper oder Export.

Erkannt werden:
- Listen mit deutschen Feldnamen (``titel``, ``zutaten`` als ``{menge, zutat}``, ``schritte`` …),
- das Format des Boards (``title``, ``ingredients``, ``steps`` …),
- schema.org/Recipe-Objekte (``name``, ``recipeIngredient``, ``recipeInstructions`` …).
Bilder werden nicht übernommen.
"""
from __future__ import annotations

import re
from typing import Any

from .i18n import T
from .recipes import _instructions, _iso_minutes, _minutes_text, _find_recipe, clean_recipe
from .textparse import OVEN, OVEN_MODE, minutes

MAX_RECIPES = 5000


class JsonImportError(Exception):
    """Fehler mit einer verständlichen Meldung für das Board."""


def _text(v: Any) -> str:
    if isinstance(v, list):
        return ", ".join(_text(x) for x in v if _text(x))
    return re.sub(r"\s+", " ", str(v or "")).strip()


def _split(v: Any) -> list[str]:
    """"Frühstück, Hauptmahlzeit" oder ["a, b", "c"] → ["Frühstück", "Hauptmahlzeit", …]"""
    items = v if isinstance(v, list) else [v]
    out: list[str] = []
    for item in items:
        out.extend(p.strip() for p in re.split(r"[,;]", str(item or "")) if p.strip())
    return out


def _tidy(text: str) -> str:
    text = re.sub(r"\(\s*,\s*", "(", text)          # "(, z. B. …)" → "(z. B. …)"
    text = re.sub(r"\s+([,.)])", r"\1", text)       # "Kichererbsensalat , Grießbrei"
    return re.sub(r"\s+", " ", text).strip()


def _ingredient(item: Any) -> str:
    if isinstance(item, dict):
        amount = _text(item.get("menge") or item.get("amount") or item.get("quantity"))
        unit = _text(item.get("einheit") or item.get("unit"))
        name = _text(item.get("zutat") or item.get("name") or item.get("ingredient") or item.get("text"))
        return _tidy(" ".join(p for p in (amount, unit, name) if p))
    return _tidy(_text(item))


def _serves(v: Any) -> int:
    m = re.search(r"\d+", _text(v))
    return int(m.group()) if m else 0


def _time(v: Any) -> str:
    text = _text(v)
    if re.fullmatch(r"P.*", text):
        return _minutes_text(_iso_minutes(text))
    total = minutes(re.sub(r"^[^:]*:\s*", "", text)) if ":" in text else minutes(text)
    return _minutes_text(total) if total else text


def _oven(steps: list[str]) -> str:
    for s in steps:
        m = OVEN.search(s)
        if m:
            mode = OVEN_MODE.search(s)
            return f"{m.group(1)} °C" + (f" {mode.group(1).capitalize()}" if mode else "")
    return ""


def _tip(extra: dict) -> str:
    """Nützliche Zusatzangaben ins Tipp-Feld; Bild und Werkzeugliste bleiben weg."""
    parts = []
    for key, value in extra.items():
        k = str(key).lower()
        if k in ("saison", "season") or any(w in k for w in ("bild", "image", "foto", "photo", "werkzeug", "tools")):
            continue  # Saison steht schon in den Tags
        text = _tidy(_text(value).replace("\n", " "))
        if text:
            parts.append(f"{key}: {text}")
    return " · ".join(parts)


def map_recipe(item: dict) -> dict | None:
    """Ein Eintrag aus der Datei → Rezept im Format des Boards (None, wenn es keins ist)."""
    if not isinstance(item, dict):
        return None
    node = _find_recipe(item)
    if node is not None:  # schema.org
        steps = _instructions(node.get("recipeInstructions"))
        total = _iso_minutes(node.get("totalTime")) or _iso_minutes(node.get("prepTime")) + _iso_minutes(node.get("cookTime"))
        data = {
            "title": node.get("name"), "description": node.get("description"), "serves": _serves(node.get("recipeYield")),
            "time": _minutes_text(total), "ingredients": [_ingredient(i) for i in node.get("recipeIngredient") or []],
            "steps": steps, "oven": _oven(steps),
            "tags": [*_split(node.get("recipeCategory")), *_split(node.get("keywords"))][:8],
        }
        source = node.get("url") or item.get("url") or ""
    else:
        get = lambda *keys: next((item[k] for k in keys if item.get(k) not in (None, "", [])), None)  # noqa: E731
        steps = [_tidy(_text(s)) for s in (get("schritte", "zubereitung", "steps", "instructions") or [])]
        if isinstance(get("schritte", "zubereitung", "steps", "instructions"), str):
            steps = _instructions(get("schritte", "zubereitung", "steps", "instructions"))
        extra = get("extra") or {}
        tags = [*_split(get("kategorie", "kategorien", "tags", "category")),
                *_split(extra.get("Saison") if isinstance(extra, dict) else "")]
        tip = " · ".join(p for p in (_text(get("tipp", "tip")), _tip(extra) if isinstance(extra, dict) else "") if p)
        data = {
            "title": get("titel", "title", "name"), "description": get("beschreibung", "description"),
            "serves": _serves(get("portionen", "serves", "servings", "yield")),
            "time": _time(get("zeit", "time", "dauer")), "oven": _text(get("ofen", "oven")) or _oven(steps),
            "ingredients": [_ingredient(i) for i in (get("zutaten", "ingredients") or [])],
            "steps": steps, "tip": tip, "tags": list(dict.fromkeys(tags))[:8],
        }
        source = get("url", "source", "quelle") or ""
    recipe = clean_recipe(data)
    if not recipe["ingredients"] and not recipe["steps"]:
        return None
    recipe["source"] = _text(source) or T("JSON-Import", "JSON import")
    return recipe


def map_file(data: Any) -> list[dict]:
    if isinstance(data, dict):
        data = data.get("recipes") or data.get("rezepte") or data.get("@graph") or [data]
    if not isinstance(data, list):
        raise JsonImportError(T("Die Datei enthält keine Liste von Rezepten.", "The file does not contain a list of recipes."))
    if len(data) > MAX_RECIPES:
        raise JsonImportError(T(f"Höchstens {MAX_RECIPES} Rezepte auf einmal.", f"At most {MAX_RECIPES} recipes at once."))
    return [r for r in (map_recipe(i) for i in data) if r]
