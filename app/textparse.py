"""Rezepttext ohne KI in ein Rezept umwandeln.

Funktioniert mit gegliedertem Text, z. B. der Ausgabe eines Texterkennungs-Programms
oder einer KI-Chat-Antwort: Titel, Angaben wie „Backzeit: 20 Minuten“, ein Abschnitt
„Zutaten“ und ein Abschnitt „Zubereitung“ – mit oder ohne Markdown.
"""
from __future__ import annotations

import re

from .i18n import T
from .recipes import _minutes_text, clean_recipe
from .units import NUM, UnitOptions, convert_text

ING = re.compile(r"^(zutaten|ingredients|du brauchst|ihr braucht|you need|you will need|einkaufsliste)\b", re.I)
STEPS = re.compile(r"^(zubereitung|anleitung|so geht'?s|schritte|arbeitsschritte|directions|instructions|method|preparation|steps)\b", re.I)
TIPS = re.compile(r"^(tipps?|tips?|hinweise?|notes?|anmerkungen?|variante|variations?)\b", re.I)

PREP = re.compile(r"(vorbereitung|zubereitungs|arbeits|prep|preparation)", re.I)
COOK = re.compile(r"(back|koch|gar|brat|ruhe|kühl|cook|bake|baking|rest|chill)", re.I)
TOTAL = re.compile(r"(gesamt|total)", re.I)
SERVES_KEY = re.compile(r"^(portionen|personen|serves|servings|for)$", re.I)
YIELD_KEY = re.compile(r"^(ergibt|yield|yields|makes|für|menge)$", re.I)
SERVES_VALUE = re.compile(r"(\d+)\s*(portionen|personen|portions|servings|people|persons)", re.I)
BULLET = re.compile(r"^\s*(?:[-*•·–]|\d+[.)]|\(\d+\))\s+")
OVEN = re.compile(r"(\d{2,3})\s*°\s*C", re.I)
OVEN_MODE = re.compile(r"(umluft|heißluft|ober-?\s*/?\s*unterhitze|fan|convection|top and bottom heat)", re.I)


def strip_md(text: str) -> str:
    text = re.sub(r"^#{1,6}\s*", "", text.strip())
    text = re.sub(r"(\*\*|__)(.+?)\1", r"\2", text)
    text = re.sub(r"(?<![\w*])([*_])(?!\s)(.+?)(?<!\s)\1(?![\w*])", r"\2", text)
    return text.replace("`", "").strip()


def nice_case(text: str) -> str:
    """GROSSBUCHSTABEN aus Kochbuch-Überschriften in normale Schreibweise bringen."""
    letters = [c for c in text if c.isalpha()]
    if letters and all(c.isupper() for c in letters):
        text = text.title()
        # In Großbuchstaben steht oft "SS" für "ß"
        text = re.sub(r"\b(S|s)osse\b", r"\1oße", text)
    return text


def minutes(text: str) -> int:
    total = 0
    for value, unit in re.findall(r"(\d+(?:[.,]\d+)?)\s*(h\b|std\.?|stunden?|hours?|hrs?\.?|min\.?|minuten|minutes?|mins?\.?)", text, re.I):
        v = float(value.replace(",", "."))
        total += v * 60 if unit.lower().startswith(("h", "std", "stun")) else v
    return int(round(total))


def _heading(line: str) -> str | None:
    """Text einer Überschrift oder None. Erkennt Markdown, fette Zeilen, GROSSBUCHSTABEN und „Zutaten:“."""
    s = line.strip()
    if re.match(r"^#{1,6}\s", s):
        return strip_md(s).rstrip(":").strip()
    m = re.fullmatch(r"(\*\*|__)([^*_]+?)\1:?", s)
    if m:
        return m.group(2).rstrip(":").strip()
    plain = strip_md(s).rstrip(":").strip()
    if not plain or len(plain) > 40 or re.search(r"\d", plain):
        return None
    if ING.match(plain) or STEPS.match(plain) or TIPS.match(plain):
        return plain
    letters = [c for c in plain if c.isalpha()]
    if len(letters) >= 3 and all(c.isupper() for c in letters):
        return plain
    if s.endswith(":") and len(plain.split()) <= 4:
        return plain
    return None


def parse_text(text: str, opts: UnitOptions | None = None) -> dict:
    opts = opts or UnitOptions()
    lines = [ln.rstrip() for ln in (text or "").splitlines()]
    # Einleitung einer Chat-Antwort ("Hier ist das Rezept …") vor der ersten Überschrift weglassen
    first_h1 = next((i for i, ln in enumerate(lines) if re.match(r"^#\s", ln.strip())), None)
    if first_h1:
        lines = lines[first_h1:]

    title, description = "", []
    meta: list[tuple[str, str]] = []
    ingredients: list[str] = []
    steps: list[str] = []
    tips: list[str] = []
    section, group = "head", ""
    found_sections = False

    for raw in lines:
        line = raw.strip()
        if not line or re.fullmatch(r"[-–—_*=]{3,}", line):
            continue
        heading = _heading(line)
        if heading is not None:
            if not title and section == "head" and not ING.match(heading) and not STEPS.match(heading):
                title = nice_case(heading)
                continue
            if ING.match(heading):
                section, group, found_sections = "ingredients", "", True
            elif STEPS.match(heading):
                section, group, found_sections = "steps", "", True
            elif TIPS.match(heading):
                section, group = "tips", ""
            elif section in ("ingredients", "steps"):
                group = nice_case(heading)  # z. B. "SOSSE" → Unterabschnitt
            continue

        if section == "head":
            m = re.match(r"^\**([^:*]{2,40}?)\**\s*:\s*\**\s*(.+?)\**$", line)
            if m and not BULLET.match(line):
                meta.append((strip_md(m.group(1)).strip(), strip_md(m.group(2)).strip()))
            else:
                description.append(strip_md(line))
            continue

        item = strip_md(BULLET.sub("", line))
        if section == "ingredients":
            ingredients.append(f"{group}: {item}" if group else item)
        elif section == "steps":
            label = re.match(r"^\*\*([^*]{1,30}?):?\*\*:?\s*(.+)$", BULLET.sub("", line))
            if label:  # "**SOSSE:** Geben Sie …"
                item = f"{nice_case(label.group(1).rstrip(':'))}: {strip_md(label.group(2))}"
            elif group and not steps_started_in_group(steps, group):
                item = f"{group}: {item}"
            steps.append(item)
        else:
            tips.append(item)

    if not found_sections:
        # Ohne Abschnitte: Zeilen mit Mengenangabe sind Zutaten, längere Sätze Schritte
        rest = description[1:] if not title and description else description
        if not title and description:
            title = nice_case(description[0])
        description = []
        for line in rest:
            if re.match(rf"^({NUM})\s*\S", line) and len(line) < 80:
                ingredients.append(line)
            elif len(line) >= 40 or steps:
                steps.append(line)
            else:
                description.append(line)

    # Angaben wie Zeiten und Portionen auswerten
    prep = cook = total = 0
    serves = 0
    for key, value in meta:
        k = key.strip().lower()
        if TOTAL.search(k) and minutes(value):
            total = minutes(value)
        elif PREP.search(k) and minutes(value):
            prep += minutes(value)
        elif COOK.search(k) and minutes(value):
            cook += minutes(value)
        elif SERVES_KEY.match(k) and re.search(r"\d+", value):
            serves = int(re.search(r"\d+", value).group())
        elif YIELD_KEY.match(k) and SERVES_VALUE.search(value):
            serves = int(SERVES_VALUE.search(value).group(1))
        else:
            tips.append(f"{nice_case(key).capitalize() if key.isupper() else key}: {value}")

    ingredients = [convert_text(i, opts) for i in ingredients]
    steps = [convert_text(s, opts) for s in steps]
    tips = [convert_text(t, opts) for t in tips]
    oven = ""
    for s in steps:
        m = OVEN.search(s)
        if m:
            mode = OVEN_MODE.search(s)
            oven = f"{m.group(1)} °C" + (f" {mode.group(1)}" if mode else "")
            break

    return clean_recipe({
        "title": title,
        "description": " ".join(description),
        "serves": serves,
        "time": _minutes_text(total or prep + cook),
        "oven": oven,
        "ingredients": ingredients,
        "steps": steps,
        "tip": " · ".join(tips),
        "tags": [],
    }) | {"source": T("Text", "Text")}


def steps_started_in_group(steps: list[str], group: str) -> bool:
    return any(s.startswith(f"{group}:") for s in steps)
