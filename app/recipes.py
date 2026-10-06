"""Rezepte: Import per Link (schema.org/Recipe als JSON-LD) und Vereinheitlichung."""
from __future__ import annotations

import html
import ipaddress
import json
import re
import socket
from typing import Any
from urllib.parse import urlparse

import httpx

from .i18n import T

RECIPE_FIELDS = ("title", "description", "serves", "time", "oven", "ingredients", "steps", "tip", "tags")

# Für die KI: ein Rezept im Format des Boards.
RECIPE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "description": {"type": "string"},
        "serves": {"type": "integer"},
        "time": {"type": "string"},
        "oven": {"type": "string"},
        "ingredients": {"type": "array", "items": {"type": "string"}},
        "steps": {"type": "array", "items": {"type": "string"}},
        "tip": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string"}},
    },
    "required": list(RECIPE_FIELDS),
    "additionalProperties": False,
}


class ImportError_(Exception):
    """Fehler beim Import, Text ist für Nutzer gedacht."""


def clean_recipe(data: dict[str, Any]) -> dict[str, Any]:
    """Bringt ein Rezept (von KI, Formular oder Import) in eine feste Form."""

    def text(v: Any) -> str:
        return re.sub(r"\s+", " ", html.unescape(str(v or ""))).strip()

    def lines(v: Any) -> list[str]:
        if isinstance(v, str):
            v = v.splitlines()
        return [t for t in (text(x) for x in (v or [])) if t]

    try:
        serves = int(data.get("serves") or 0)
    except (TypeError, ValueError):
        m = re.search(r"\d+", str(data.get("serves")))
        serves = int(m.group()) if m else 0
    tags = data.get("tags") or []
    if isinstance(tags, str):
        tags = tags.split(",")
    return {
        "title": text(data.get("title")) or T("Ohne Titel", "Untitled"),
        "description": text(data.get("description")),
        "serves": max(serves, 0),
        "time": text(data.get("time")),
        "oven": text(data.get("oven")),
        "ingredients": lines(data.get("ingredients")),
        "steps": lines(data.get("steps")),
        "tip": text(data.get("tip")),
        "tags": sorted({t for t in (text(x) for x in tags) if t}, key=str.lower),
    }


# Hinweise auf nicht-metrische Angaben (z. B. bei englischen Rezeptseiten).
IMPERIAL = re.compile(r"\b(cups?|tbsp|tsp|tablespoons?|teaspoons?|ounces?|oz|lbs?|pounds?|quarts?|pints?|sticks?)\b|°\s*F\b|\d\s*F\b", re.I)


def needs_metric(recipe: dict[str, Any]) -> bool:
    blob = " ".join([recipe.get("oven", ""), *recipe.get("ingredients", []), *recipe.get("steps", [])])
    return bool(IMPERIAL.search(blob))


# ---------- Import per Link ----------

def _check_url(url: str) -> None:
    """Nur öffentliche http(s)-Adressen – das Board soll nicht ins eigene Heimnetz greifen."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ImportError_(T("Bitte einen vollständigen Link angeben, der mit https:// beginnt.", "Please enter a full link starting with https://."))
    try:
        infos = socket.getaddrinfo(parsed.hostname, None)
    except socket.gaierror as e:
        raise ImportError_(T("Die Adresse wurde nicht gefunden.", "The address could not be found.")) from e
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global:
            raise ImportError_(T("Links ins lokale Netz werden nicht abgerufen.", "Links into the local network are not fetched."))


async def fetch_page(url: str) -> str:
    _check_url(url)
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) SupperBoard/1.0",
        "Accept-Language": "de-DE,de;q=0.9",
    }
    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=False, headers=headers) as client:
            r = await client.get(url)
            for _ in range(5):  # Weiterleitungen einzeln prüfen
                if not r.is_redirect:
                    break
                url = str(r.url.join(r.headers["location"]))
                _check_url(url)
                r = await client.get(url)
    except httpx.HTTPError as e:
        raise ImportError_(T("Die Seite konnte nicht geladen werden.", "The page could not be loaded.")) from e
    if r.status_code >= 400:
        raise ImportError_(T(f"Die Seite antwortet mit Fehler {r.status_code}.", f"The page returned error {r.status_code}."))
    return r.text[:3_000_000]


def _iso_minutes(value: Any) -> int:
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:\d+S)?", str(value or "").strip())
    if not m:
        return 0
    d, h, mi = (int(x or 0) for x in m.groups())
    return d * 1440 + h * 60 + mi


def _minutes_text(minutes: int) -> str:
    if minutes <= 0:
        return ""
    h, m = divmod(minutes, 60)
    if h and m:
        return T(f"{h} Std. {m} Min.", f"{h} h {m} min")
    return (T(f"{h} Std.", f"{h} h") if h else T(f"{m} Min.", f"{m} min"))


def _types(node: dict) -> list[str]:
    t = node.get("@type", [])
    return [t] if isinstance(t, str) else list(t)


def _find_recipe(node: Any) -> dict | None:
    if isinstance(node, list):
        for item in node:
            found = _find_recipe(item)
            if found:
                return found
    elif isinstance(node, dict):
        if "Recipe" in _types(node):
            return node
        for key in ("@graph", "mainEntity", "itemListElement"):
            if key in node:
                found = _find_recipe(node[key])
                if found:
                    return found
    return None


def _instructions(value: Any) -> list[str]:
    if isinstance(value, str):
        parts = re.split(r"\n+|(?<=[.!?])\s{2,}", html.unescape(re.sub(r"<[^>]+>", "\n", value)))
        return [p.strip() for p in parts if p.strip()]
    steps: list[str] = []
    for item in value or []:
        if isinstance(item, str):
            steps.extend(_instructions(item))
        elif isinstance(item, dict):
            if "HowToSection" in _types(item):
                steps.extend(_instructions(item.get("itemListElement")))
            elif item.get("text"):
                steps.append(str(item["text"]))
            elif item.get("name"):
                steps.append(str(item["name"]))
    return steps


def parse_jsonld(page: str) -> dict | None:
    for raw in re.findall(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', page, re.S | re.I):
        try:
            data = json.loads(raw.strip())
        except json.JSONDecodeError:
            continue
        node = _find_recipe(data)
        if not node:
            continue
        total = _iso_minutes(node.get("totalTime")) or (_iso_minutes(node.get("prepTime")) + _iso_minutes(node.get("cookTime")))
        yield_ = node.get("recipeYield")
        if isinstance(yield_, list):
            yield_ = next((y for y in yield_ if re.search(r"\d", str(y))), yield_[0] if yield_ else "")
        keywords = node.get("keywords") or []
        if isinstance(keywords, str):
            keywords = keywords.split(",")
        category = node.get("recipeCategory") or []
        if isinstance(category, str):
            category = [category]
        return clean_recipe({
            "title": node.get("name"),
            "description": node.get("description"),
            "serves": yield_,
            "time": _minutes_text(total),
            "ingredients": node.get("recipeIngredient") or node.get("ingredients"),
            "steps": _instructions(node.get("recipeInstructions")),
            "tags": [*category, *keywords][:8],
        })
    return None


def page_text(page: str) -> str:
    """Grober Seitentext für die KI, falls die Seite keine Rezeptdaten mitliefert."""
    page = re.sub(r"<(script|style|noscript|svg)[^>]*>.*?</\1>", " ", page, flags=re.S | re.I)
    text = html.unescape(re.sub(r"<[^>]+>", "\n", page))
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text[:40_000]
