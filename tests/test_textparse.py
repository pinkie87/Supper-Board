import pytest
from fastapi.testclient import TestClient

from app import i18n
from app.main import create_app
from app.textparse import parse_text
from app.units import UnitOptions, convert_text, metric, nice, parse_number

# Eigenes Beispiel im Stil einer KI-Chat-Antwort auf ein Kochbuchfoto (übersetztes US-Kochbuch)
MARKDOWN = """Hier ist das Rezept aus dem Foto als Text:

---

# KÜRBIS-MUFFINS

**SCHWIERIGKEIT:** Einfach
**VORBEREITUNGSZEIT:** 15 Minuten
**BACKZEIT:** 25 Minuten
**ERGIBT:** 12 Muffins

*Saftig, würzig und perfekt für den Herbst.*

## Zutaten

- 2 Tassen Mehl
- ½ gehäufte Tasse brauner Zucker
- 1 Pfund Kürbispüree
- 2 Esslöffel Öl
- 1 ½ Teelöffel Zimt
- 1 Ei

### GLASUR

- 1 Tasse Puderzucker
- 2-3 Esslöffel Milch

## Zubereitung

1. Den Ofen auf **350°F** (Umluft) vorheizen.
2. Alles verrühren und in eine 12er-Muffinform füllen.

**GLASUR:** Puderzucker mit der Milch glatt rühren und über die Muffins geben.
"""

PLAIN = """Linsensuppe
Für 4 Portionen
250 g rote Linsen
1 Zwiebel
1 l Gemüsebrühe
Die Zwiebel fein würfeln und in etwas Öl glasig dünsten.
Linsen und Brühe zugeben und 15 Minuten köcheln lassen, dann pürieren.
"""


@pytest.mark.parametrize("text,value", [("½", 0.5), ("1½", 1.5), ("1 ½", 1.5), ("1 1/2", 1.5), ("3/4", 0.75), ("0,5", 0.5), ("2", 2)])
def test_parse_number(text, value):
    assert parse_number(text) == pytest.approx(value)


@pytest.mark.parametrize("value,expected", [(453.6, 450), (226.8, 225), (340.2, 350), (375, 375), (360, 350), (480, 500),
                                            (240, 250), (680.4, 700), (907.2, 900), (28.35, 30), (113, 110), (5, 5),
                                            (125, 125), (250, 250), (62.5, 60), (12.5, 13)])
def test_nice_rounding(value, expected):
    assert nice(value) == expected


def test_metric_uses_kg_and_l():
    assert metric(1361, "g") == "1,4 kg"
    assert metric(3785, "ml") == "3,75 l"


def test_convert_us_and_de():
    us, de = UnitOptions(origin="us"), UnitOptions(origin="de")
    assert convert_text("1 Pfund Hackfleisch", us) == "450 g Hackfleisch"
    assert convert_text("1 Pfund Hackfleisch", de) == "500 g Hackfleisch"
    assert convert_text("1½ Tassen Milch", us) == "350 ml Milch"
    assert convert_text("1½ Tassen Milch", de) == "375 ml Milch"
    assert convert_text("8 oz cream cheese", us) == "225 g cream cheese"
    assert convert_text("2 tbsp butter", us) == "2 EL butter"
    assert convert_text("Bake at 350°F for 20 minutes", us) == "Bake at 175 °C for 20 minutes"
    assert convert_text("Eine 9 inch Form", us) == "Eine 23 cm Form"
    assert convert_text("4 Eier und 2 Zwiebeln", us) == "4 Eier und 2 Zwiebeln"


def test_convert_options():
    keep = UnitOptions(weight="keep", volume="keep", spoons="ml")
    assert convert_text("1 Pfund Mehl", keep) == "1 Pfund Mehl"
    assert convert_text("1 Tasse Milch", keep) == "1 Tasse Milch"
    assert convert_text("2 Esslöffel Öl", keep) == "30 ml Öl"
    assert convert_text("½ gehäufte Tasse Zucker", UnitOptions()) == "120 ml (gehäuft) Zucker"
    assert convert_text("2-3 Esslöffel Milch", UnitOptions()) == "2–3 EL Milch"
    assert convert_text("2-3 Tassen Brühe", UnitOptions()) == "500–700 ml Brühe"


def test_english_spoon_names():
    i18n.set_lang("en")
    assert convert_text("2 Esslöffel Öl", UnitOptions()) == "2 tbsp Öl"


def test_parse_markdown_recipe():
    r = parse_text(MARKDOWN)
    assert r["title"] == "Kürbis-Muffins"
    assert r["description"] == "Saftig, würzig und perfekt für den Herbst."
    assert r["time"] == "40 Min."
    assert r["oven"] == "175 °C Umluft"
    assert r["ingredients"][:6] == ["500 ml Mehl", "120 ml (gehäuft) brauner Zucker", "450 g Kürbispüree",
                                    "2 EL Öl", "1½ TL Zimt", "1 Ei"]
    assert r["ingredients"][6:] == ["Glasur: 250 ml Puderzucker", "Glasur: 2–3 EL Milch"]
    assert r["steps"][0] == "Den Ofen auf 175 °C (Umluft) vorheizen."
    assert r["steps"][-1].startswith("Glasur: Puderzucker mit der Milch")
    assert "Schwierigkeit: Einfach" in r["tip"] and "Ergibt: 12 Muffins" in r["tip"]
    assert r["serves"] == 0
    assert r["source"] == "Text"


def test_parse_plain_text_without_headings():
    r = parse_text(PLAIN)
    assert r["title"] == "Linsensuppe"
    assert r["ingredients"] == ["250 g rote Linsen", "1 Zwiebel", "1 l Gemüsebrühe"]
    assert len(r["steps"]) == 2
    assert r["description"] == "Für 4 Portionen"


def test_parse_serves_and_english_headings():
    text = "# Pancakes\nServes: 4\nPrep time: 10 min\nCook time: 1 h\n\n## Ingredients\n- 1 cup flour\n\n## Instructions\n1. Mix.\n2. Fry."
    r = parse_text(text)
    assert r["serves"] == 4 and r["time"] == "1 Std. 10 Min."
    assert r["ingredients"] == ["250 ml flour"] and r["steps"] == ["Mix.", "Fry."]


def test_parse_text_endpoint_without_ai(settings):
    with TestClient(create_app(settings, run_scheduler=False)) as c:
        r = c.post("/api/recipes/parse-text", json={"text": MARKDOWN, "units": {"origin": "de", "spoons": "ml"}})
        assert r.status_code == 200
        body = r.json()
        assert "500 g Kürbispüree" in body["ingredients"] and "30 ml Öl" in body["ingredients"]
        bad = c.post("/api/recipes/parse-text", json={"text": "Nur ein Satz ohne Rezept darin."})
        assert bad.status_code == 400
