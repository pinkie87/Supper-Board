"""Sprache: Deutsch (Standard) oder Englisch.

Der Haushalt wählt die Sprache im Board (gespeichert in ``plan/settings``);
``SB_LANGUAGE`` gilt nur, solange noch niemand gewählt hat. Texte vom Server
(Benachrichtigungen, Einkaufslisten, Fehlermeldungen, KI-Ausgaben) folgen der
aktuellen Sprache, die pro Anfrage bzw. Aufgabe in einer Kontextvariablen steht.
"""
from __future__ import annotations

from contextvars import ContextVar

LANGUAGES = ("de", "en")
_default = "de"
_current: ContextVar[str | None] = ContextVar("lang", default=None)


def set_default(code: str) -> None:
    global _default
    _default = code if code in LANGUAGES else "de"


def set_lang(code: str | None) -> None:
    _current.set(code if code in LANGUAGES else None)


def lang() -> str:
    return _current.get() or _default


def T(de: str, en: str) -> str:
    """Deutschen oder englischen Text passend zur aktuellen Sprache wählen."""
    return en if lang() == "en" else de


def household_lang(store) -> str:
    doc = store.get("plan", "settings") or {}
    code = doc.get("language")
    return code if code in LANGUAGES else _default


def use_household(store) -> str:
    code = household_lang(store)
    set_lang(code)
    return code
