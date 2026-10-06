# Hinweise für Claude

## Dokumentation immer zweisprachig

Jede Dokumentation gibt es auf Deutsch und auf Englisch. Wer eine Seite ändert oder neu anlegt, pflegt beide Fassungen im selben Commit.

- `README.md`: oben die englische Fassung (`## English`), darunter die deutsche (`## Deutsch`), mit gleichem Inhalt und gleicher Gliederung.
- Anleitungen: deutsch in `docs/`, englisch in `docs/en/`. Zuordnung:

  | Deutsch | Englisch |
  |---|---|
  | `docs/einrichtung-fedora.md` | `docs/en/setup-fedora.md` |
  | `docs/home-assistant.md` | `docs/en/home-assistant.md` |
  | `docs/ki.md` | `docs/en/ai.md` |
  | `docs/datenmodell.md` | `docs/en/data-model.md` |
  | `docs/kuechen-tablet.md` | `docs/en/kitchen-tablet.md` |

- Jede Seite beginnt mit einem Sprachumschalter, z. B. `[English](en/ai.md) · **Deutsch**` bzw. `**English** · [Deutsch](../ki.md)`. Neue Seiten in diese Tabelle aufnehmen.
- Englische Texte verlinken auf englische Seiten, deutsche auf deutsche.
- Bezeichnungen aus der Oberfläche (z. B. „Plan freigeben“) bleiben auch im englischen Text deutsch, weil das Board deutsch ist.

## Projekt

- Server: `app/` (FastAPI, SQLite), Board: `web/index.html` + `web/db.js`.
- Tests: `python -m pytest` – vor jedem Commit ausführen.
- Oberfläche, Rezepte und Server-Meldungen sind deutsch, Einheiten metrisch.
