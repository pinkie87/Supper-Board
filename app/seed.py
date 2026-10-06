"""Startdaten beim allerersten Start: Richtlinien und typischer Grundvorrat."""
from __future__ import annotations

from .store import Store

GUIDELINES = (
    "Zwei Erwachsene. Kochen an drei Abenden pro Woche (Mo/Mi/Fr) mit Portionen für zwei Abende, "
    "am Folgetag gibt es Reste. Sonntag ist flexibel. Unter der Woche höchstens 45 Minuten Arbeitszeit. "
    "Ausgewogen, viel Gemüse, ein- bis zweimal pro Woche Fisch, mindestens ein vegetarisches Gericht pro Woche."
)

STAPLES = {
    "Vorrat": ["Nudeln", "Reis", "Mehl", "Zucker", "Haferflocken", "Gehackte Tomaten (Dose)", "Kokosmilch", "Gemüsebrühe"],
    "Öl, Essig & Soßen": ["Olivenöl", "Rapsöl", "Balsamico", "Senf", "Sojasoße", "Tomatenmark"],
    "Gewürze": ["Salz", "Pfeffer", "Paprikapulver edelsüß", "Currypulver", "Oregano", "Kreuzkümmel"],
    "Kühlschrank & Frisch": ["Butter", "Parmesan", "Zwiebeln", "Knoblauch", "Kartoffeln"],
}


def seed(store: Store) -> None:
    if store.get("plan", "current") is None:
        store.set("plan", "current", {"status": "active", "guidelines": GUIDELINES})
    if not store.list("staples"):
        order = 0
        for group, names in STAPLES.items():
            for name in names:
                order += 1
                store.add("staples", {"name": name, "group": group, "status": "have", "order": order})
