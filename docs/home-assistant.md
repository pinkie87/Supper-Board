[English](en/home-assistant.md) · **Deutsch**

# Home Assistant einbinden

Supper Board schickt Benachrichtigungen über die `notify`-Dienste von Home Assistant – z. B. an die Companion-App auf euren Handys. Zusätzlich kann Home Assistant abfragen, was es heute gibt, und das im Dashboard oder in eigenen Automationen verwenden.

## Benachrichtigungen

Die Nachrichten kommen in der Sprache des Boards (Deutsch oder Englisch). **Was verschickt wird:**

| Wann | Nachricht |
|---|---|
| Neuer Planentwurf | „Neuer Speiseplan 12.10.–25.10.: … Bitte bis Donnerstag ansehen und freigeben.“ |
| Einkaufsliste fertig | „Die Einkaufsliste für Sa. 17.10. ist fertig (32 Artikel).“ |
| Am Vorabend (`SB_THAW_TIME`, Standard 20:00) | „Vor dem Schlafengehen: die Hähnchenbrust (ca. 600 g) aus dem Gefrierfach in den Kühlschrank legen – für morgen: Hähnchen-Curry.“ |
| Optional täglich (`SB_DINNER_TIME`) | „Heute wird gekocht: Ofengemüse mit Feta (45 Min.).“ |
| Fehler | z. B. wenn die KI nicht erreichbar war |

Mit gesetztem `SB_PUBLIC_URL` öffnet ein Tippen auf die Nachricht direkt das Board.

**Einrichten:**

1. In Home Assistant: **Profil → Sicherheit → Langlebige Zugriffstoken → Token erstellen**. Den Token kopieren.
2. Den Namen eurer Benachrichtigungsdienste herausfinden: **Entwicklerwerkzeuge → Aktionen**, nach `notify.` suchen. Für die Companion-App heißen sie z. B. `notify.mobile_app_pixel_8`.
3. In der `.env` eintragen:

   ```ini
   HA_URL=http://homeassistant.local:8123
   HA_TOKEN=eyJhbGciOi...
   HA_NOTIFY=notify.mobile_app_pixel_8,notify.mobile_app_iphone
   ```

   Läuft Home Assistant auf demselben Rechner wie der Container, statt `localhost` die IP-Adresse des Servers oder `host.containers.internal` verwenden.
4. Dienst neu starten (`systemctl --user restart supper-board`) und im Board unter **Feedback → Einrichtung → Home Assistant → Test senden** prüfen.

## Sensor „Heute Abend“

Der Server liefert unter `/api/ha/today` eine kleine Übersicht:

```json
{
  "tonight": "Ofengemüse mit Feta",
  "tonight_kind": "cook",
  "tomorrow": "Reste: Ofengemüse mit Feta",
  "thaw_tonight": "",
  "status": "active",
  "next_order_items": 3
}
```

In der `configuration.yaml` von Home Assistant:

```yaml
rest:
  - resource: http://fedora.local:8080/api/ha/today
    authentication: basic
    username: ha
    password: !secret supper_board_password
    scan_interval: 900
    sensor:
      - name: "Abendessen heute"
        value_template: "{{ value_json.tonight or 'nichts geplant' }}"
        icon: mdi:silverware-fork-knife
      - name: "Abendessen morgen"
        value_template: "{{ value_json.tomorrow or 'nichts geplant' }}"
      - name: "Heute auftauen"
        value_template: "{{ value_json.thaw_tonight or 'nichts' }}"
        icon: mdi:snowflake
```

Ohne `SB_PASSWORD` die drei Zeilen `authentication`, `username` und `password` weglassen.

**Beispiel-Automation:** Erinnerung auf dem Küchenlautsprecher, wenn etwas aufgetaut werden muss.

```yaml
automation:
  - alias: "Auftauen ansagen"
    triggers:
      - trigger: time
        at: "19:30:00"
    conditions:
      - condition: template
        value_template: "{{ states('sensor.heute_auftauen') not in ['nichts', 'unknown', 'unavailable'] }}"
    actions:
      - action: tts.speak
        target:
          entity_id: tts.google_translate_de_de
        data:
          media_player_entity_id: media_player.kueche
          message: "Bitte {{ states('sensor.heute_auftauen') }} in den Kühlschrank legen."
```
