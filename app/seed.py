"""Startdaten beim allerersten Start: Richtlinien und typischer Grundvorrat."""
from __future__ import annotations

from .store import Store

GUIDELINES = {
    "de": (
        "Zwei Erwachsene. Kochen an drei Abenden pro Woche (Mo/Mi/Fr) mit Portionen für zwei Abende, "
        "am Folgetag gibt es Reste. Sonntag ist flexibel. Unter der Woche höchstens 45 Minuten Arbeitszeit. "
        "Ausgewogen, viel Gemüse, ein- bis zweimal pro Woche Fisch, mindestens ein vegetarisches Gericht pro Woche."
    ),
    "en": (
        "Two adults. Cook three nights a week (Mon/Wed/Fri) with portions for two nights; "
        "leftovers the next day. Sunday is flexible. At most 45 minutes of hands-on time on weeknights. "
        "Balanced, plenty of vegetables, fish once or twice a week, at least one vegetarian meal per week."
    ),
}

STAPLES = {
    "de": {
        "Vorrat": ["Nudeln", "Reis", "Mehl", "Zucker", "Haferflocken", "Gehackte Tomaten (Dose)", "Kokosmilch", "Gemüsebrühe"],
        "Öl, Essig & Soßen": ["Olivenöl", "Rapsöl", "Balsamico", "Senf", "Sojasoße", "Tomatenmark"],
        "Gewürze": ["Salz", "Pfeffer", "Paprikapulver edelsüß", "Currypulver", "Oregano", "Kreuzkümmel"],
        "Kühlschrank & Frisch": ["Butter", "Parmesan", "Zwiebeln", "Knoblauch", "Kartoffeln"],
    },
    "en": {
        "Pantry": ["Pasta", "Rice", "Flour", "Sugar", "Oats", "Chopped tomatoes (tin)", "Coconut milk", "Vegetable stock"],
        "Oils, vinegar & sauces": ["Olive oil", "Rapeseed oil", "Balsamic vinegar", "Mustard", "Soy sauce", "Tomato paste"],
        "Spices": ["Salt", "Pepper", "Sweet paprika", "Curry powder", "Oregano", "Cumin"],
        "Fridge & fresh": ["Butter", "Parmesan", "Onions", "Garlic", "Potatoes"],
    },
}


def seed(store: Store, language: str = "de") -> None:
    language = language if language in GUIDELINES else "de"
    if store.get("plan", "current") is None:
        store.set("plan", "current", {"status": "active", "guidelines": GUIDELINES[language]})
    if not store.list("staples"):
        order = 0
        for group, names in STAPLES[language].items():
            for name in names:
                order += 1
                store.add("staples", {"name": name, "group": group, "status": "have", "order": order})
