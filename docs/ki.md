# KI einrichten

Die KI schreibt neue Speisepläne, ersetzt Gerichte, die ihr ablehnt, wandelt eingefügte Rezepttexte um und erfindet Rezepte auf Wunsch. Umschalten in der `.env` mit `LLM_PROVIDER` und danach den Dienst neu starten.

| `LLM_PROVIDER` | Was passiert | Datenschutz |
|---|---|---|
| `claude` | Claude über die Anthropic-API. Beste Rezeptqualität. | Beim Planen gehen Richtlinien, Bewertungen, Notizen, Wünsche, Vorrat, Gefrierschrank und die Titel eurer Rezepte an Anthropic. Alles andere bleibt auf dem Server. |
| `ollama` | Lokales Modell über [Ollama](https://ollama.com). | Nichts verlässt das Heimnetz. |
| `none` | Keine KI. Pläne werden aus der Rezeptdatenbank zusammengestellt (gut bewertete zuerst, mit Abwechslung). | Nichts verlässt den Server. |

Ohne KI funktioniert alles andere weiter: Rezepte per Formular oder Link anlegen, Plan aus der Datenbank, Einkaufsliste, Erinnerungen.

## Claude

1. Auf <https://console.anthropic.com/> ein Konto anlegen, Guthaben aufladen und einen API-Schlüssel erstellen.
2. In der `.env`:

   ```ini
   LLM_PROVIDER=claude
   ANTHROPIC_API_KEY=sk-ant-...
   CLAUDE_MODEL=claude-opus-5-5
   CLAUDE_EFFORT=medium
   ```

- `CLAUDE_MODEL`: Standard ist Claude Opus 5.5. Günstiger ist `claude-sonnet-5-5`.
- `CLAUDE_EFFORT`: wie gründlich das Modell nachdenkt (`low`, `medium`, `high`). `medium` reicht für Speisepläne gut.
- Lehnt das Modell eine Anfrage ausnahmsweise ab, übernimmt automatisch ein Ersatzmodell (serverseitiger Fallback der Anthropic-API).

Kosten: Ein Zwei-Wochen-Plan mit allen Rezepten kostet mit Opus grob 10–50 Cent, ein einzelnes Rezept etwa 1–5 Cent. Die genauen Preise stehen auf der Anthropic-Website.

## Ollama

1. Ollama auf dem Server (oder einem Rechner im Netz mit Grafikkarte) installieren:

   ```bash
   curl -fsSL https://ollama.com/install.sh | sh
   ollama pull qwen3:14b
   ```

2. Damit der Container Ollama erreicht, muss Ollama auf allen Schnittstellen lauschen:

   ```bash
   sudo systemctl edit ollama
   # einfügen:
   # [Service]
   # Environment="OLLAMA_HOST=0.0.0.0"
   sudo systemctl restart ollama
   ```

3. In der `.env`:

   ```ini
   LLM_PROVIDER=ollama
   OLLAMA_URL=http://host.containers.internal:11434
   OLLAMA_MODEL=qwen3:14b
   ```

**Welches Modell?** Ein Zwei-Wochen-Plan ist eine lange, strukturierte Antwort. Modelle ab etwa 14 Milliarden Parametern (z. B. `qwen3:14b`, `gemma3:27b`, `mistral-small`) liefern brauchbare deutsche Rezepte; kleinere Modelle erfinden öfter unpassende Mengen. Ohne Grafikkarte kann ein Plan mehrere Minuten dauern – das Board zeigt währenddessen „… schreibt gerade den Speiseplan“.
