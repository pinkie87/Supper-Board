# Hinweise für Claude

## Commits und Pull Requests auf Englisch

Commit-Nachrichten, Branch-Namen, Titel und Beschreibungen von Pull Requests sowie Kommentare auf GitHub immer auf Englisch schreiben, damit auch Außenstehende den Verlauf verstehen. Beispiel: „Add English translations of the guides“ statt „Dokumentation auf Englisch ergänzt“.

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
- Bezeichnungen aus der Oberfläche in der jeweiligen Sprache nennen: deutsch „Plan freigeben“, englisch "Approve plan".

## Projekt

- Server: `app/` (FastAPI, SQLite), Board: `web/index.html` + `web/db.js`.
- Tests: `python -m pytest` – vor jedem Commit ausführen.
- Oberfläche und Server-Meldungen gibt es auf Deutsch und Englisch; die Sprache stellt der Haushalt im Board ein (`plan/settings`), Einheiten sind immer metrisch.
- Neue Texte im Board immer zweisprachig: in `web/index.html` als `L("deutsch", "english")`, feste Texte im HTML zusätzlich in `STATIC_EN`; auf dem Server mit `T("deutsch", "english")` aus `app/i18n.py`.
