import json

import pytest

from app import recipes

PAGE = """<html><head>
<script type="application/ld+json">{"@context":"https://schema.org","@type":"BreadcrumbList"}</script>
<script type="application/ld+json">%s</script>
</head><body>…</body></html>"""

CHEFKOCH_LIKE = {
    "@context": "https://schema.org",
    "@graph": [
        {"@type": "WebPage", "name": "Seite"},
        {
            "@type": ["Recipe"],
            "name": "Spaghetti Aglio e Olio",
            "description": "Schnell &amp; einfach",
            "recipeYield": ["2", "2 Portionen"],
            "prepTime": "PT10M",
            "cookTime": "PT15M",
            "recipeIngredient": ["200 g Spaghetti", "3 Zehen Knoblauch", "  6 EL Olivenöl "],
            "recipeInstructions": [
                {"@type": "HowToSection", "name": "Nudeln", "itemListElement": [
                    {"@type": "HowToStep", "text": "Spaghetti in Salzwasser kochen."}]},
                {"@type": "HowToStep", "text": "Knoblauch in Öl anbraten."},
            ],
            "keywords": "Pasta, schnell",
            "recipeCategory": "Hauptspeise",
        },
    ],
}


def test_parse_jsonld_graph_and_sections():
    r = recipes.parse_jsonld(PAGE % json.dumps(CHEFKOCH_LIKE))
    assert r["title"] == "Spaghetti Aglio e Olio"
    assert r["description"] == "Schnell & einfach"
    assert r["serves"] == 2
    assert r["time"] == "25 Min."
    assert r["ingredients"] == ["200 g Spaghetti", "3 Zehen Knoblauch", "6 EL Olivenöl"]
    assert r["steps"] == ["Spaghetti in Salzwasser kochen.", "Knoblauch in Öl anbraten."]
    assert r["tags"] == ["Hauptspeise", "Pasta", "schnell"]


def test_parse_jsonld_string_instructions_and_hours():
    data = {"@type": "Recipe", "name": "Braten", "totalTime": "PT1H30M", "recipeYield": "4 Portionen",
            "recipeInstructions": "Anbraten.<br>Schmoren.", "recipeIngredient": ["1 kg Rind"]}
    r = recipes.parse_jsonld(PAGE % json.dumps(data))
    assert r["time"] == "1 Std. 30 Min."
    assert r["serves"] == 4
    assert r["steps"] == ["Anbraten.", "Schmoren."]


def test_parse_jsonld_none_without_recipe():
    assert recipes.parse_jsonld("<html><body>Kein Rezept</body></html>") is None


def test_needs_metric():
    assert recipes.needs_metric({"ingredients": ["2 cups flour"], "steps": [], "oven": ""})
    assert recipes.needs_metric({"ingredients": [], "steps": ["Bake at 350 F"], "oven": ""})
    assert not recipes.needs_metric({"ingredients": ["250 g Mehl", "1 TL Salz"], "steps": ["Bei 180 °C backen"], "oven": ""})


def test_clean_recipe_normalizes():
    r = recipes.clean_recipe({"title": " Suppe ", "serves": "für 3", "ingredients": "a\n\nb", "tags": "b, a, a"})
    assert r["title"] == "Suppe" and r["serves"] == 3
    assert r["ingredients"] == ["a", "b"]
    assert r["tags"] == ["a", "b"]


@pytest.mark.parametrize("url", ["http://127.0.0.1/x", "http://localhost/", "file:///etc/passwd", "http://192.168.1.10/"])
def test_check_url_blocks_local(url):
    with pytest.raises(recipes.ImportError_):
        recipes._check_url(url)
