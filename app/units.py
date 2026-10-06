"""Einheiten umrechnen und auf praxistaugliche Werte runden (450 g statt 454 g)."""
from __future__ import annotations

import math
import re
from dataclasses import dataclass

from .i18n import T

FRACTIONS = {"½": 0.5, "¼": 0.25, "¾": 0.75, "⅓": 1 / 3, "⅔": 2 / 3, "⅛": 0.125, "⅜": 0.375, "⅝": 0.625, "⅞": 0.875}
_UF = "½¼¾⅓⅔⅛⅜⅝⅞"
# Reihenfolge wichtig: "1 1/2" vor "1", "1½" als Ganzes
NUM = rf"(?:\d+\s+\d+/\d+|\d+/\d+|\d+(?:[.,]\d+)?\s?[{_UF}]?|[{_UF}])"


@dataclass
class UnitOptions:
    origin: str = "us"        # "us": Pfund 454 g, Tasse 240 ml – "de": Pfund 500 g, Tasse 250 ml
    weight: str = "metric"    # "metric" (g/kg) oder "keep"
    volume: str = "metric"    # "metric" (ml/l) oder "keep"
    spoons: str = "spoons"    # "spoons" (EL/TL) oder "ml"

    @classmethod
    def from_dict(cls, data: dict | None) -> "UnitOptions":
        data = data or {}
        return cls(
            origin=data.get("origin") if data.get("origin") in ("us", "de") else "us",
            weight=data.get("weight") if data.get("weight") in ("metric", "keep") else "metric",
            volume=data.get("volume") if data.get("volume") in ("metric", "keep") else "metric",
            spoons=data.get("spoons") if data.get("spoons") in ("spoons", "ml") else "spoons",
        )


def parse_number(text: str) -> float:
    s = text.strip().replace(",", ".")
    m = re.fullmatch(r"(\d+)\s+(\d+)/(\d+)", s)
    if m:
        return int(m.group(1)) + int(m.group(2)) / int(m.group(3))
    m = re.fullmatch(r"(\d+)/(\d+)", s)
    if m:
        return int(m.group(1)) / int(m.group(2))
    m = re.fullmatch(rf"(\d+(?:\.\d+)?)?\s?([{_UF}])?", s)
    if m and (m.group(1) or m.group(2)):
        return float(m.group(1) or 0) + FRACTIONS.get(m.group(2) or "", 0)
    raise ValueError(text)


def nice(value: float) -> float:
    """Auf Werte runden, die man in der Küche wirklich abwiegt bzw. abmisst: die gröbste
    Stufe, die höchstens ein paar Prozent abweicht (454 → 450, 375 → 375, 480 → 500)."""
    if value <= 0:
        return 0
    if value >= 100 and abs(value / 25 - round(value / 25)) < 0.002:
        return round(value / 25) * 25  # schon rund (125, 375 …) – so lassen
    if value < 50:
        steps, tolerance = (5, 1), 0.10
    elif value < 200:
        steps, tolerance = (10, 5), 0.05
    elif value < 1000:
        steps, tolerance = (50, 25, 10), 0.05
    else:
        steps, tolerance = (500, 250, 100), 0.05
    for step in steps:
        rounded = math.floor(value / step + 0.5) * step  # .5 immer aufrunden
        if rounded > 0 and abs(rounded - value) / value <= tolerance:
            return rounded
    return max(steps[-1], math.floor(value / steps[-1] + 0.5) * steps[-1])


def fmt_number(value: float) -> str:
    text = f"{value:.2f}".rstrip("0").rstrip(".") if value != int(value) else str(int(value))
    return text.replace(".", T(",", "."))


def fmt_amount(value: float) -> str:
    """Brüche wie ½ für Löffel und Stück lesbar lassen."""
    whole, frac = int(value), value - int(value)
    for sym, f in FRACTIONS.items():
        if abs(frac - f) < 0.01:
            return (f"{whole}{sym}" if whole else sym)
    return fmt_number(round(value, 2))


def metric(value: float, base: str) -> str:
    """value in g oder ml → '450 g', '1,5 kg', '350 ml', '1,2 l'."""
    v = nice(value)
    if v >= 1000:
        return f"{fmt_number(v / 1000)} {'kg' if base == 'g' else 'l'}"
    return f"{fmt_number(v)} {base}"


ADJ = r"(?:(?P<adj>gehäufte?[rnms]?|gestrichene?[rnms]?|großzügige?[rnms]?|knappe?[rnms]?|volle?[rnms]?|heaping|heaped|level|scant|generous|rounded)\s+)?"

# Einheit → (Art, Faktor für US, Faktor für DE); Art: g, ml, spoon_el, spoon_tl
UNITS: list[tuple[str, str, float, float]] = [
    (r"fl\.?\s?oz\.?|fluid\s+ounces?|flüssigunzen?", "ml", 29.57, 29.57),
    (r"pfund|pfd\.?|lbs?\.?|pounds?", "g", 453.6, 500.0),
    (r"unzen?|oz\.?|ounces?", "g", 28.35, 28.35),
    (r"tassen?|cups?", "ml", 240.0, 250.0),
    (r"pints?", "ml", 473.0, 500.0),
    (r"quarts?", "ml", 946.0, 1000.0),
    (r"gallonen|gallons?", "ml", 3785.0, 3785.0),
    (r"esslöffeln?|eßlöffeln?|el|tbsp\.?|tbs\.?|tablespoons?", "spoon_el", 15.0, 15.0),
    (r"teelöffeln?|tl|tsp\.?|teaspoons?", "spoon_tl", 5.0, 5.0),
]
_UNIT_RE = re.compile(
    rf"(?<![\w/])(?P<a>{NUM})(?:\s*(?:-|–|bis|to)\s*(?P<b>{NUM}))?\s*{ADJ}(?P<u>{'|'.join(f'(?:{u[0]})' for u in UNITS)})(?![\wäöüß])",
    re.I,
)
_FAHRENHEIT = re.compile(rf"(?P<a>{NUM})\s*(?:°\s?F\b|grad\s+fahrenheit|degrees?\s+f(?:ahrenheit)?\b|F\b(?=[\s.,;)]|$))", re.I)
_INCH = re.compile(rf"(?P<a>{NUM})\s*(?:zoll|inch(?:es)?|″|\")(?![\w])", re.I)


def _unit_for(text: str) -> tuple[str, float, float]:
    for pattern, kind, us, de in UNITS:
        if re.fullmatch(pattern, text, re.I):
            return kind, us, de
    raise KeyError(text)


def _adj_note(adj: str | None) -> str:
    if not adj:
        return ""
    a = adj.lower()
    if a.startswith(("gehäuft", "heap", "rounded")):
        return T(" (gehäuft)", " (heaped)")
    if a.startswith(("gestrichen", "level")):
        return T(" (gestrichen)", " (level)")
    if a.startswith(("knapp", "scant")):
        return T(" (knapp)", " (scant)")
    return T(" (großzügig)", " (generous)")


def convert_text(text: str, opts: UnitOptions) -> str:
    """Rechnet alle erkannten Mengenangaben in einem Text um (Zutat, Schritt oder Tipp)."""

    def repl(m: re.Match) -> str:
        kind, us, de = _unit_for(m.group("u"))
        factor = us if opts.origin == "us" else de
        try:
            a = parse_number(m.group("a"))
            b = parse_number(m.group("b")) if m.group("b") else None
        except ValueError:
            return m.group(0)
        note = _adj_note(m.group("adj"))
        if kind in ("spoon_el", "spoon_tl"):
            if opts.spoons == "ml":
                if b is not None:
                    return f"{fmt_number(nice(a * factor))}–{metric(b * factor, 'ml')}{note}"
                return metric(a * factor, "ml") + note
            unit = T("EL", "tbsp") if kind == "spoon_el" else T("TL", "tsp")
            amount = fmt_amount(a) + (f"–{fmt_amount(b)}" if b is not None else "")
            return f"{amount} {unit}{note}"
        if (kind == "g" and opts.weight == "keep") or (kind == "ml" and opts.volume == "keep"):
            return m.group(0)
        if b is not None:
            low, high = metric(a * factor, kind), metric(b * factor, kind)
            if low.split()[-1] == high.split()[-1]:
                low = low.rsplit(" ", 1)[0]
            return f"{low}–{high}{note}"
        return metric(a * factor, kind) + note

    def fahrenheit(m: re.Match) -> str:
        try:
            f = parse_number(m.group("a"))
        except ValueError:
            return m.group(0)
        return f"{int(round((f - 32) * 5 / 9 / 5) * 5)} °C"

    def inch(m: re.Match) -> str:
        try:
            cm = parse_number(m.group("a")) * 2.54
        except ValueError:
            return m.group(0)
        return f"{fmt_number(max(1, round(cm)))} cm"

    text = _UNIT_RE.sub(repl, text)
    text = _FAHRENHEIT.sub(fahrenheit, text)
    return _INCH.sub(inch, text)
