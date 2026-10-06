[English](en/ai.md) · **Deutsch**

# KI einrichten

Die KI schreibt neue Speisepläne, ersetzt Gerichte, die ihr ablehnt, wandelt eingefügte Rezepttexte um, liest Rezepte von Fotos und erfindet Rezepte auf Wunsch. Umschalten in der `.env` mit `LLM_PROVIDER` und danach den Dienst neu starten. Rezepte und Pläne schreibt die KI in der Sprache des Boards (Deutsch oder Englisch), immer metrisch.

| `LLM_PROVIDER` | Was passiert | Datenschutz |
|---|---|---|
| `claude` | Claude über die Anthropic-API. Beste Rezeptqualität. | Beim Planen gehen Richtlinien, Bewertungen, Notizen, Wünsche, Vorrat, Gefrierschrank und die Titel eurer Rezepte an Anthropic. Alles andere bleibt auf dem Server. |
| `ollama` | Lokales Modell über [Ollama](https://ollama.com), auf dem Server oder deinem PC. | Nichts verlässt das Heimnetz. |
| `openai` | OpenAI-kompatible Schnittstelle: lokal (llama.cpp, LM Studio, auch mit Unsloth-Modellen) oder in der Cloud (Google Gemini, OpenRouter – mit kostenlosem Kontingent). | Lokal: nichts verlässt das Heimnetz. Cloud: wie bei Claude, siehe unten. |
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

## Ollama (auf dem Server oder auf deinem PC)

Ollama kann auf dem Server selbst laufen oder auf einem anderen Rechner im Heimnetz, z. B. deinem PC mit Grafikkarte. Das Board ruft es über das Netzwerk auf.

1. Ollama installieren (Linux; für Windows und macOS gibt es Installer auf [ollama.com](https://ollama.com)) und Modelle laden:

   ```bash
   curl -fsSL https://ollama.com/install.sh | sh
   ollama pull qwen3:14b       # Textmodell für Pläne und Rezepte
   ollama pull qwen2.5vl:7b    # Bildmodell für Fotos von Rezeptseiten
   ```

2. Ollama muss auf allen Netzwerkschnittstellen lauschen, nicht nur auf `localhost`:
   - **Linux:** `sudo systemctl edit ollama`, dort `[Service]` und `Environment="OLLAMA_HOST=0.0.0.0"` eintragen, dann `sudo systemctl restart ollama`.
   - **Windows:** Umgebungsvariable `OLLAMA_HOST` mit dem Wert `0.0.0.0` anlegen und Ollama neu starten. In der Windows-Firewall eingehende Verbindungen auf Port 11434 aus dem Heimnetz erlauben.

3. In der `.env` auf dem Server:

   ```ini
   LLM_PROVIDER=ollama
   # Ollama auf dem Server selbst:
   OLLAMA_URL=http://host.containers.internal:11434
   # Ollama auf deinem PC (IP-Adresse des PCs):
   # OLLAMA_URL=http://192.168.178.20:11434
   OLLAMA_MODEL=qwen3:14b
   OLLAMA_VISION_MODEL=qwen2.5vl:7b
   ```

   Ob der Server den PC erreicht, zeigt `curl http://192.168.178.20:11434/api/tags` auf dem Server. Gib dem PC im Router am besten eine feste IP-Adresse.

**Welches Modell?** Ein Zwei-Wochen-Plan ist eine lange, strukturierte Antwort. Modelle ab etwa 14 Milliarden Parametern (z. B. `qwen3:14b`, `gemma3:12b`, `mistral-small`) liefern brauchbare Rezepte; kleinere Modelle erfinden öfter unpassende Mengen. Ohne Grafikkarte kann ein Plan mehrere Minuten dauern – das Board zeigt währenddessen „… schreibt gerade den Speiseplan“.

## Rezepte von Fotos einlesen

Unter „Rezepte → Von Foto importieren“ lassen sich Fotos von Kochbuchseiten oder handgeschriebenen Rezepten hochladen. Dafür braucht es ein **Bildmodell**:

- **Ollama:** `OLLAMA_VISION_MODEL`, z. B. `qwen2.5vl:7b` (liest Text auf Fotos gut, braucht ca. 6–8 GB Grafikspeicher), `gemma3:12b` oder – falls in deiner Ollama-Version vorhanden – `qwen3-vl:8b`. Ohne Eintrag wird `OLLAMA_MODEL` verwendet; das funktioniert nur, wenn dieses Modell selbst Bilder versteht (z. B. `gemma3`).
- **OpenAI-kompatibler Server:** `OPENAI_VISION_MODEL` (siehe unten).
- **Claude:** liest Fotos ohne weitere Einstellung.

So läuft der Import:

1. „Jedes Foto einzeln einlesen“ für ein Buch Seite für Seite; „Alle Fotos gehören zu einem Rezept“, wenn ein Rezept über mehrere Seiten geht.
2. Das Board verkleinert die Fotos vor dem Hochladen (längste Seite 2000 Pixel). Der Server liest sie im Hintergrund nacheinander in der hochgeladenen Reihenfolge – die Seite darf dabei geschlossen werden.
3. Unter „Foto-Import“ erscheint jedes gefundene Rezept mit „Prüfen“. Das Formular zeigt das Foto zum Vergleich; erst „Speichern“ legt das Rezept in der Datenbank an. Danach wird das Foto gelöscht.
4. Ist der PC mit der KI aus, steht das Foto auf „Fehler“. Später „Erneut versuchen“ bzw. „Alle mit Fehler erneut versuchen“ antippen.

Die Fotos liegen bis zum Speichern oder Verwerfen in `uploads/` im Datenverzeichnis des Servers. Tipps: eine Seite pro Foto, gerade von oben, gutes Licht, kein Blitz. Unleserliche Stellen markiert die KI mit `[?]`.

## Text umwandeln – auch ohne KI

Unter „Rezepte → Text umwandeln“ wird eingefügter Rezepttext zum Rezept, z. B. die Ausgabe einer Texterkennung oder einer KI im Browser.

- **„Umwandeln“** braucht keine KI und funktioniert auch, wenn der PC aus ist. Es erkennt Titel, Angaben wie Vorbereitungs- und Backzeit oder Portionen, die Abschnitte „Zutaten“ und „Zubereitung“ (auch Unterabschnitte wie „Soße“) und die Ofentemperatur. Am besten klappt es mit gegliedertem Text, etwa mit Markdown-Überschriften.
- **„Mit KI umwandeln“** (nur mit eingerichteter KI) kommt auch mit ungeordnetem Text zurecht und rechnet trockene Zutaten in Tassen in Gramm um.

Einstellungen für die Umrechnung (merkt sich das Board pro Gerät):

| Schalter | Möglichkeiten |
|---|---|
| Maße im Text | amerikanisch (Pfund 454 g, Tasse 240 ml) oder deutsch (Pfund 500 g, Tasse 250 ml) |
| Gewichte | in g/kg umrechnen oder so lassen |
| Tassen & Flüssigmaße | in ml/l umrechnen oder so lassen |
| Löffel | als EL/TL oder in ml |

Umgerechnete Werte werden auf praxistaugliche Zahlen gerundet: 454 g → 450 g, 355 ml → 350 ml, 1,5 Tassen (deutsch) → 375 ml, 350 °F → 175 °C. Fahrenheit wird immer in °C umgerechnet, Zoll in cm.

## OpenAI-kompatibler Server (llama.cpp, LM Studio, vLLM, Unsloth-Modelle)

Viele lokale Programme bieten dieselbe Schnittstelle wie OpenAI an: `llama-server` aus [llama.cpp](https://github.com/ggml-org/llama.cpp), LM Studio oder vLLM. Damit lassen sich z. B. die quantisierten GGUF-Modelle von [Unsloth](https://huggingface.co/unsloth) nutzen. (Viele Unsloth-GGUF-Modelle laufen auch direkt in Ollama: `ollama run hf.co/unsloth/<Modell>-GGUF`.)

Beispiel mit `llama-server` auf dem PC, ein Bildmodell mit Projektor-Datei (`mmproj`):

```bash
llama-server -m Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf --mmproj mmproj-F16.gguf --host 0.0.0.0 --port 8080
```

In der `.env`:

```ini
LLM_PROVIDER=openai
OPENAI_URL=http://192.168.178.20:8080/v1
OPENAI_MODEL=local
# Nur nötig, wenn für Fotos ein anderes Modell geladen ist (z. B. in LM Studio):
OPENAI_VISION_MODEL=
# Nur nötig, wenn der Server einen Schlüssel verlangt:
OPENAI_API_KEY=
```

Das Board fordert die Antwort als JSON nach Schema an; kennt ein Server das nicht, fragt es ohne Schema noch einmal nach.

## Google Gemini oder OpenRouter (Cloud, kostenloses Kontingent)

Beide bieten eine OpenAI-kompatible Schnittstelle und kostenlose Modelle an. Sie laufen über `LLM_PROVIDER=openai`; das Board erkennt den Anbieter an der Adresse und zeigt seinen Namen an. Dein PC muss dafür nicht laufen.

**Google Gemini**

1. In [Google AI Studio](https://aistudio.google.com/) mit einem Google-Konto anmelden und einen API-Schlüssel erstellen.
2. In der `.env`:

   ```ini
   LLM_PROVIDER=openai
   OPENAI_URL=https://generativelanguage.googleapis.com/v1beta/openai
   OPENAI_API_KEY=<dein Schlüssel>
   OPENAI_MODEL=gemini-2.5-flash
   ```

   Gemini-Modelle verstehen auch Fotos, `OPENAI_VISION_MODEL` kann leer bleiben. Die aktuellen Modellnamen stehen in AI Studio.

**OpenRouter**

1. Auf [openrouter.ai](https://openrouter.ai/) ein Konto anlegen und unter „Keys“ einen API-Schlüssel erstellen.
2. Ein kostenloses Modell aussuchen: In der [Modellliste](https://openrouter.ai/models) nach „free“ filtern – die Namen enden auf `:free`. Für den Foto-Import ein Modell mit Bild-Eingabe („image“) wählen.
3. In der `.env`:

   ```ini
   LLM_PROVIDER=openai
   OPENAI_URL=https://openrouter.ai/api/v1
   OPENAI_API_KEY=sk-or-...
   OPENAI_MODEL=<anbieter>/<modell>:free
   # Falls das Textmodell keine Bilder versteht:
   OPENAI_VISION_MODEL=<anbieter>/<bildmodell>:free
   ```

   Manche kostenlosen Modelle sind nur nutzbar, wenn in den OpenRouter-Einstellungen unter „Privacy“ die entsprechenden Anbieter erlaubt sind.

**Grenzen der kostenlosen Kontingente:** Es gibt Limits pro Minute und pro Tag; wie hoch, legen die Anbieter fest und ändern es gelegentlich. Meldet der Anbieter „zu viele Anfragen“, pausiert der Foto-Import und macht automatisch weiter (Wartezeit wächst bis höchstens eine Stunde) – ein ganzes Buch dauert so eventuell mehrere Tage, läuft aber ohne dein Zutun. „Erneut versuchen“ startet sofort einen neuen Versuch. Der Planentwurf braucht nur eine Anfrage pro Woche.

**Datenschutz:** Bei kostenlosen Angeboten können Anbieter die gesendeten Daten zur Verbesserung ihrer Modelle verwenden. Gesendet werden beim Planen Richtlinien, Bewertungen, Notizen, Wünsche, Vorrat, Gefrierschrank und Rezepttitel, beim Foto-Import die Fotos. Wer das nicht möchte, nimmt Ollama auf dem eigenen PC.

## Wenn der PC nicht läuft

Läuft die KI auf deinem PC, muss er zu den eingestellten Zeiten an sein (Planentwurf `SB_DRAFT_DAY`/`SB_DRAFT_TIME`, Einkaufsliste `SB_LIST_DAY`/`SB_LIST_TIME`). Ist er aus, zeigt das Board „Das hat nicht geklappt“ und – falls eingerichtet – Home Assistant schickt eine Nachricht. Dann einfach später „Nächsten Plan jetzt erstellen“ bzw. „Einkaufsliste jetzt erstellen“ antippen. Fotos warten mit „Fehler“, bis du sie erneut versuchst.
