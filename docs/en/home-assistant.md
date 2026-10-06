**English** · [Deutsch](../home-assistant.md)

# Home Assistant integration

Supper Board sends notifications through Home Assistant's `notify` services, for example to the Companion app on your phones. Home Assistant can also ask what's for dinner and use it on a dashboard or in your own automations.

## Notifications

The messages themselves are in German. **What gets sent:**

| When | Message (example, translated) |
|---|---|
| New plan drafted | "New meal plan 12.10.–25.10.: … Please review and approve it on Supper Board by Thursday." |
| Shopping list ready | "The shopping list for Sat 17.10. is ready (32 items)." |
| The evening before (`SB_THAW_TIME`, default 20:00) | "Before bed: move the chicken breast (approx. 600 g) from the freezer to the fridge – for tomorrow: chicken curry." |
| Optional, daily (`SB_DINNER_TIME`) | "Cooking tonight: roasted vegetables with feta (45 min)." |
| Errors | e.g. when the AI could not be reached |

With `SB_PUBLIC_URL` set, tapping the notification opens the board.

**Setup:**

1. In Home Assistant: **Profile → Security → Long-lived access tokens → Create token**. Copy the token.
2. Find the names of your notification services: **Developer tools → Actions**, search for `notify.`. For the Companion app they look like `notify.mobile_app_pixel_8`.
3. Add them to `.env`:

   ```ini
   HA_URL=http://homeassistant.local:8123
   HA_TOKEN=eyJhbGciOi...
   HA_NOTIFY=notify.mobile_app_pixel_8,notify.mobile_app_iphone
   ```

   If Home Assistant runs on the same machine as the container, use the server's IP address or `host.containers.internal` instead of `localhost`.
4. Restart the service (`systemctl --user restart supper-board`) and test it in the board under **Feedback → Einrichtung → Home Assistant → Test senden**.

## "Dinner tonight" sensor

The server provides a small summary at `/api/ha/today`:

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

In Home Assistant's `configuration.yaml`:

```yaml
rest:
  - resource: http://fedora.local:8080/api/ha/today
    authentication: basic
    username: ha
    password: !secret supper_board_password
    scan_interval: 900
    sensor:
      - name: "Dinner tonight"
        value_template: "{{ value_json.tonight or 'nothing planned' }}"
        icon: mdi:silverware-fork-knife
      - name: "Dinner tomorrow"
        value_template: "{{ value_json.tomorrow or 'nothing planned' }}"
      - name: "Thaw tonight"
        value_template: "{{ value_json.thaw_tonight or 'nothing' }}"
        icon: mdi:snowflake
```

Without `SB_PASSWORD`, leave out the three lines `authentication`, `username` and `password`.

**Example automation:** a reminder on the kitchen speaker when something needs thawing.

```yaml
automation:
  - alias: "Announce thawing"
    triggers:
      - trigger: time
        at: "19:30:00"
    conditions:
      - condition: template
        value_template: "{{ states('sensor.thaw_tonight') not in ['nothing', 'unknown', 'unavailable'] }}"
    actions:
      - action: tts.speak
        target:
          entity_id: tts.google_translate_en_com
        data:
          media_player_entity_id: media_player.kitchen
          message: "Please move {{ states('sensor.thaw_tonight') }} to the fridge."
```
