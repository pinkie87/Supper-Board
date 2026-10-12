import asyncio

import pytest
from fastapi.testclient import TestClient

from app import htmlrecipe, linkimport, recipes
from app.main import create_app

# Eigene Beispielseiten, angelehnt an typische Rezeptseiten
JSONLD = """<html><head><script type="application/ld+json">{"@context":"https://schema.org","@type":"Recipe",
"name":"Linsen-Dal","image":"https://example.org/dal.jpg","recipeYield":"4 Portionen","totalTime":"PT35M",
"recipeIngredient":["250 g rote Linsen","1 Zwiebel"],"recipeInstructions":[{"@type":"HowToStep","text":"Zwiebel dünsten."},
{"@type":"HowToStep","text":"Linsen kochen."}]}</script></head><body><h1>Linsen-Dal</h1></body></html>"""

MICRODATA = """<html><body><div itemscope itemtype="https://schema.org/Recipe">
<h1 itemprop="name">Gefüllte Paprika</h1><img itemprop="image" src="p.jpg">
<span itemprop="recipeYield">2 Portionen</span>
<ul><li itemprop="recipeIngredient">2 Paprika</li><li itemprop="recipeIngredient">150 g Reis</li></ul>
<div itemprop="recipeInstructions"><ol><li>Reis garen.</li><li>Paprika füllen und backen.</li></ol></div>
</div></body></html>"""

PLAIN = """<html><head><title>Auberginen | Beispielseite</title></head><body>
<nav><ul><li>Start</li><li>Rezepte</li></ul></nav>
<main><h1>Auberginenschiffchen</h1><p>Für 2 Personen</p>
<h2>Zutaten</h2><ul><li>2 Auberginen</li><li>200 g Tomaten</li><li>1 EL Öl</li></ul>
<h2>Zubereitung</h2><ol><li>Auberginen halbieren und aushöhlen.</li><li>Füllen und bei 200 °C backen.</li></ol>
<h2>Ähnliche Rezepte</h2><ul><li>Zucchini-Schiffchen</li></ul></main>
<footer><ul><li>Impressum</li></ul></footer></body></html>"""

LIST = """<html><body><nav><a href="/">Start</a><a href="/rezeptdatenbank">Rezepte</a></nav>
<a href="/rezeptdatenbank?tx_wwrecipe_fe1%5Bcat%5D%5B4%5D=37&amp;tx_wwrecipe_fe1%5Bsearch%5D=1">Filter</a>
<a href="/rezeptdatenbank/rezept/linsen-dal"><img src="a.jpg"></a>
<a href="/rezeptdatenbank/rezept/linsen-dal">Linsen-Dal</a>
<a href="/rezeptdatenbank?tx_wwrecipe_fe1%5Brecipe%5D=12&amp;tx_wwrecipe_fe1%5Baction%5D=show">Ofengemüse</a>
<a href="https://other.example/rezept/x">Fremd</a><a href="/rezepte/suche?tx_wwrecipe_fe1%5Bsearchtext%5D=dal">Suche</a><a href="/bilder/x.jpg">Bild</a>
<nav class="pages"><a href="/rezeptdatenbank?page=2" rel="next">Weiter</a></nav></body></html>"""


def test_extract_jsonld_without_image():
    r = htmlrecipe.extract_recipe(JSONLD)
    assert r["title"] == "Linsen-Dal" and r["serves"] == 4 and r["ingredients"] == ["250 g rote Linsen", "1 Zwiebel"]
    assert "image" not in r


def test_extract_microdata():
    r = htmlrecipe.extract_recipe(MICRODATA)
    assert r["title"] == "Gefüllte Paprika" and r["serves"] == 2
    assert r["ingredients"] == ["2 Paprika", "150 g Reis"] and r["steps"] == ["Reis garen.", "Paprika füllen und backen."]


def test_extract_from_page_text():
    r = htmlrecipe.extract_recipe(PLAIN)
    assert r["title"] == "Auberginenschiffchen"
    assert r["ingredients"] == ["2 Auberginen", "200 g Tomaten", "1 EL Öl"]
    assert r["steps"] == ["Auberginen halbieren und aushöhlen.", "Füllen und bei 200 °C backen."]
    assert r["oven"] == "200 °C" and "Zucchini" not in " ".join(r["steps"])


def test_no_recipe():
    assert htmlrecipe.extract_recipe("<html><body><h1>Hallo</h1><p>Nichts zu essen.</p></body></html>") is None


def test_find_links():
    found = htmlrecipe.find_links(LIST, "https://example.org/rezeptdatenbank?tx_wwrecipe_fe1%5Bsearch%5D=1")
    urls = [link["url"] for link in found["links"]]
    assert urls == ["https://example.org/rezeptdatenbank/rezept/linsen-dal",
                    "https://example.org/rezeptdatenbank?tx_wwrecipe_fe1%5Brecipe%5D=12&tx_wwrecipe_fe1%5Baction%5D=show"]
    assert found["links"][0]["title"] == "Linsen-Dal"
    assert found["next"] == "https://example.org/rezeptdatenbank?page=2"


def test_create_link_imports_skips_known(store):
    store.set("recipes", "r1", {"title": "Dal", "source": "https://example.org/a"})
    res = linkimport.create_link_imports(store, ["https://example.org/a/", "https://example.org/b", "https://example.org/b#x", ""])
    assert len(res["ids"]) == 1 and res["skipped"] == 1
    assert linkimport.create_link_imports(store, ["https://example.org/b"])["skipped"] == 1
    with pytest.raises(linkimport.LinkError):
        linkimport.create_link_imports(store, ["kein link"])


def test_read_link(store, settings, monkeypatch):
    pages = {"https://example.org/a": PLAIN, "https://example.org/b": "<html><body>leer</body></html>"}

    async def fake_fetch(url):
        return pages[url]

    monkeypatch.setattr(recipes, "fetch_page", fake_fetch)
    ids = linkimport.create_link_imports(store, list(pages))["ids"]
    for i in ids:
        asyncio.run(linkimport.read_link(store, settings, i))
    ok, bad = (store.get("imports", i) for i in ids)
    assert ok["state"] == "done" and ok["recipes"][0]["source"] == "https://example.org/a"
    assert ok["title"] == "Auberginenschiffchen"
    assert bad["state"] == "error" and "kein Rezept" in bad["message"]


def test_link_endpoints_and_worker_without_ai(settings, monkeypatch):
    async def fake_fetch(url):
        return LIST if "liste" in url else JSONLD

    monkeypatch.setattr(recipes, "fetch_page", fake_fetch)
    monkeypatch.setattr(linkimport, "DELAY", 0)
    with TestClient(create_app(settings, run_scheduler=False)) as c:
        found = c.post("/api/recipes/find-links", json={"url": "https://example.org/liste"}).json()
        assert len(found["links"]) == 2
        assert c.post("/api/imports/links", json={"urls": []}).status_code == 400
        res = c.post("/api/imports/links", json={"urls": [found["links"][0]["url"]]}).json()
        doc_id = res["ids"][0]
        for _ in range(50):
            doc = c.get(f"/api/db/imports/{doc_id}").json()
            if doc["state"] == "done":
                break
            asyncio.run(asyncio.sleep(0.05))
        assert doc["state"] == "done" and doc["recipes"][0]["title"] == "Linsen-Dal"
