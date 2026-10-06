from fastapi.testclient import TestClient

from app import llm, planner, versions
from app.main import create_app

RECIPE = {"title": "Linsensuppe", "serves": 4, "ingredients": ["250 g rote Linsen", "1 Zwiebel"],
          "steps": ["Zwiebel dünsten.", "Linsen kochen."], "tags": [], "source": "Text", "createdAt": "2026-10-01T10:00:00"}


def client(settings):
    return TestClient(create_app(settings, run_scheduler=False))


def test_versions_on_save(store):
    first = versions.save(store, "r1", dict(RECIPE))
    assert first["version"] == 1 and first["versionNote"] == "Angelegt"
    versions.save(store, "r1", dict(RECIPE))  # nichts geändert → keine neue Version
    assert store.get("recipes", "r1")["version"] == 1 and versions.list_versions(store, "r1") == []

    changed = versions.save(store, "r1", dict(RECIPE, ingredients=["250 g rote Linsen", "2 Zwiebeln"]), "mehr Zwiebel")
    assert changed["version"] == 2 and changed["versionNote"] == "mehr Zwiebel"
    assert changed["createdAt"] == RECIPE["createdAt"]
    old = versions.list_versions(store, "r1")
    assert len(old) == 1 and old[0]["version"] == 1 and old[0]["data"]["ingredients"][1] == "1 Zwiebel"
    assert "version" not in old[0]["data"]

    restored = versions.restore(store, "r1", old[0]["id"])
    assert restored["version"] == 3 and restored["ingredients"][1] == "1 Zwiebel"
    assert restored["versionNote"] == "Version 1 wiederhergestellt"
    assert [v["version"] for v in versions.list_versions(store, "r1")] == [2, 1]
    assert versions.restore(store, "anderes", old[0]["id"]) is None


def test_versions_are_pruned(store, monkeypatch):
    monkeypatch.setattr(versions, "KEEP", 3)
    for n in range(6):
        versions.save(store, "r1", dict(RECIPE, title=f"Suppe {n}"))
    assert [v["version"] for v in versions.list_versions(store, "r1")] == [5, 4, 3]
    assert store.get("recipes", "r1")["version"] == 6


def test_missing_and_empty_fields_are_the_same(store):
    store.set("recipes", "r1", {k: v for k, v in RECIPE.items() if k != "tags"})  # älteres Rezept ohne Tags, ohne Tipp
    saved = versions.save(store, "r1", dict(RECIPE, tip="", oven="", description=""))
    assert saved["version"] == 1 and versions.list_versions(store, "r1") == []


def test_restore_of_identical_version_is_recorded(store):
    versions.save(store, "r1", dict(RECIPE))
    versions.save(store, "r1", dict(RECIPE, title="Rote Linsensuppe"))
    v1 = versions.list_versions(store, "r1")[0]
    versions.restore(store, "r1", v1["id"])  # Version 3 = Inhalt von Version 1
    again = versions.restore(store, "r1", v1["id"])
    assert again["version"] == 4 and again["versionNote"] == "Version 1 wiederhergestellt"


def test_timestamps_have_timezone(store):
    saved = versions.save(store, "r1", dict(RECIPE))
    assert saved["updatedAt"].endswith("+00:00")


def test_meal_saved_as_recipe_gets_version(store):
    meal = {"title": "Ofengemüse", "details": "", "recipe": {"serves": 2, "ingredients": ["1 Zucchini"], "steps": ["Backen."]}}
    rid = planner.save_meal_as_recipe(store, meal)
    doc = store.get("recipes", rid)
    assert doc["version"] == 1 and doc["updatedAt"] and doc["createdAt"].endswith("+00:00")


def test_api_versions_and_delete(settings):
    with client(settings) as c:
        rid = c.post("/api/db/recipes", json=RECIPE).json()["id"]
        assert c.get(f"/api/db/recipes/{rid}").json()["version"] == 1
        assert c.put(f"/api/db/recipes/{rid}", json=dict(RECIPE, title="Rote Linsensuppe", _note="Titel")).status_code == 200
        doc = c.get(f"/api/db/recipes/{rid}").json()
        assert doc["version"] == 2 and doc["versionNote"] == "Titel" and "_note" not in doc
        assert c.patch(f"/api/db/recipes/{rid}", json={"serves": 2}).status_code == 200
        assert c.get(f"/api/db/recipes/{rid}").json()["version"] == 3
        vs = c.get(f"/api/recipes/{rid}/versions").json()
        assert [v["version"] for v in vs] == [2, 1]
        assert c.post(f"/api/recipes/{rid}/versions/{vs[1]['id']}/restore").status_code == 200
        assert c.get(f"/api/db/recipes/{rid}").json()["title"] == "Linsensuppe"
        assert c.post(f"/api/recipes/{rid}/versions/fehlt/restore").status_code == 404
        c.delete(f"/api/db/recipes/{rid}")
        assert c.get(f"/api/recipes/{rid}/versions").json() == []


def test_ai_review(settings, monkeypatch):
    settings.llm_provider = "ollama"
    calls = []

    async def fake(s, system, prompt, schema, images=None):
        calls.append(prompt)
        return {"recipe": dict(RECIPE, title="Linsensuppe (vegan)", tags=["vegan"]), "changes": ["Butter durch Öl ersetzt", " "]}

    monkeypatch.setattr(llm, "generate_json", fake)
    with client(settings) as c:
        rid = c.post("/api/db/recipes", json=RECIPE).json()["id"]
        assert c.post(f"/api/recipes/{rid}/ai-review", json={"mode": "variant"}).status_code == 400
        r = c.post(f"/api/recipes/{rid}/ai-review", json={"mode": "variant", "wish": "vegan"})
        assert r.status_code == 200
        body = r.json()
        assert body["recipe"]["title"] == "Linsensuppe (vegan)" and body["recipe"]["source"] == "Text"
        assert body["changes"] == ["Butter durch Öl ersetzt"] and body["note"] == "KI: vegan"
        assert "vegan" in calls[-1] and "250 g rote Linsen" in calls[-1]
        # Der Vorschlag wird erst beim Speichern übernommen
        assert c.get(f"/api/db/recipes/{rid}").json()["version"] == 1

        body = c.post(f"/api/recipes/{rid}/ai-review", json={"mode": "check"}, headers={"X-Lang": "en"}).json()
        assert body["note"] == "AI: checked and corrected" and "Prüfe dieses Rezept" in calls[-1]
        assert c.post("/api/recipes/fehlt/ai-review", json={"mode": "check"}).status_code == 404


def test_ai_review_needs_ai(settings):
    with client(settings) as c:
        rid = c.post("/api/db/recipes", json=RECIPE).json()["id"]
        assert c.post(f"/api/recipes/{rid}/ai-review", json={"mode": "check"}).status_code == 400
