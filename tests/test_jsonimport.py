from fastapi.testclient import TestClient

from app import jsonimport
from app.main import create_app

# Eigenes Beispiel im Aufbau einer Scraper-Ausgabe mit deutschen Feldnamen
SCRAPED = [{
    "quelle": "example.org", "url": "https://example.org/rezept/ofengemuese/", "titel": "Ofengemüse",
    "beschreibung": "", "kategorie": ["Hauptmahlzeit, Beilage"], "portionen": "4 Portionen", "zeit": "Gesamtzeit: 1 Std 5 Min",
    "zutaten": [{"menge": "600", "zutat": "g Kartoffeln"}, {"menge": "0,5", "zutat": "Zucchini (, z. B. grün)"}, {"menge": "", "zutat": "Salz"}],
    "schritte": ["Den Ofen auf 200 °C (Umluft) vorheizen.", "Gemüse schneiden und 40 Minuten backen."],
    "naehrwerte": [],
    "extra": {"Saison": "Sommer, Herbst", "Allergene": "keine", "Dazu passt": "Kräuterquark , Salat",
              "Küchenwerkzeuge": ["Messer"], "(Saisonale) Alternativen": "Frühling: Spargel\nHerbst: Kürbis", "Bild": "https://example.org/bild.jpg"},
}, {"titel": "Leer", "zutaten": [], "schritte": []}]

SCHEMA = {"@context": "https://schema.org", "@type": "Recipe", "name": "Porridge", "recipeYield": "2", "totalTime": "PT10M",
          "recipeIngredient": ["80 g Haferflocken", "300 ml Milch"], "recipeInstructions": [{"@type": "HowToStep", "text": "Aufkochen."}],
          "url": "https://example.org/porridge", "image": "https://example.org/p.jpg"}


def test_map_scraped_recipe():
    recipes = jsonimport.map_file(SCRAPED)
    assert len(recipes) == 1
    r = recipes[0]
    assert r["title"] == "Ofengemüse" and r["serves"] == 4 and r["time"] == "1 Std. 5 Min."
    assert r["ingredients"] == ["600 g Kartoffeln", "0,5 Zucchini (z. B. grün)", "Salz"]
    assert r["oven"] == "200 °C Umluft"
    assert r["tags"] == ["Beilage", "Hauptmahlzeit", "Herbst", "Sommer"]
    assert r["tip"] == "Allergene: keine · Dazu passt: Kräuterquark, Salat · (Saisonale) Alternativen: Frühling: Spargel Herbst: Kürbis"
    assert r["source"] == "https://example.org/rezept/ofengemuese/"
    assert "Bild" not in r["tip"] and "image" not in r


def test_map_schema_and_board_format():
    r = jsonimport.map_file({"recipes": [SCHEMA]})[0]
    assert r["title"] == "Porridge" and r["serves"] == 2 and r["time"] == "10 Min." and r["steps"] == ["Aufkochen."]
    own = jsonimport.map_file([{"title": "Toast", "ingredients": ["2 Scheiben Brot"], "steps": ["Toasten."], "serves": 1}])[0]
    assert own["title"] == "Toast" and own["source"] == "JSON-Import"


def test_import_endpoint(settings):
    with TestClient(create_app(settings, run_scheduler=False)) as c:
        assert c.post("/api/recipes/import-json", json={"data": "kaputt"}).status_code == 400
        r = c.post("/api/recipes/import-json", json={"data": SCRAPED + [SCHEMA]}).json()
        assert r == {"added": 2, "skipped": 0, "total": 2}
        saved = {x["title"]: x for x in c.get("/api/db/recipes").json()}
        assert saved["Ofengemüse"]["version"] == 1 and saved["Ofengemüse"]["versionNote"] == "JSON-Import"
        again = c.post("/api/recipes/import-json", json={"data": SCRAPED, "mode": "review"}).json()
        assert again["added"] == 0 and again["skipped"] == 1
        review = c.post("/api/recipes/import-json", json={"data": [dict(SCRAPED[0], url="https://example.org/neu")], "mode": "review"}).json()
        assert review["added"] == 1
        imp = [i for i in c.get("/api/db/imports").json() if i.get("kind") == "file"]
        assert len(imp) == 1 and imp[0]["state"] == "done" and imp[0]["recipes"][0]["title"] == "Ofengemüse"
