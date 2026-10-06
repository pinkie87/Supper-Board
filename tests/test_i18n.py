import asyncio
from datetime import date

from fastapi.testclient import TestClient

from app import i18n, llm, planner
from app.main import create_app
from app.seed import seed


def run(coro):
    return asyncio.run(coro)


def english(store):
    store.set("plan", "settings", {"language": "en"})
    i18n.use_household(store)


def test_T_follows_language():
    assert i18n.T("Hallo", "Hello") == "Hallo"
    i18n.set_lang("en")
    assert i18n.T("Hallo", "Hello") == "Hello"
    i18n.set_lang("xx")  # unbekannt -> Standard
    assert i18n.lang() == "de"


def test_household_setting_overrides_default(store):
    i18n.set_default("en")
    assert i18n.household_lang(store) == "en"
    store.set("plan", "settings", {"language": "de"})
    assert i18n.household_lang(store) == "de"


def test_english_plan_and_list(store, settings, monkeypatch):
    monkeypatch.setattr(planner, "today", lambda s: date(2026, 10, 6))
    seed(store, "en")
    english(store)
    for i in range(4):
        store.add("recipes", {"title": f"Dish {i}", "ingredients": [f"{i} g x"], "steps": ["Cook."]})
    msg = run(planner.draft_plan(store, settings, force=True))
    assert msg.startswith("New meal plan 12 Oct–25 Oct:") and "by Thursday" in msg
    assert store.get("plan", "draft")["pickup"] == "Sat 10 Oct"
    titles = {m["title"] for m in store.list("draft")}
    assert "Free choice" in titles and any(t.startswith("Leftovers: ") for t in titles)
    store.add("grocery", {"text": "Coffee", "at": "1"})
    monkeypatch.setattr(planner, "today", lambda s: date(2026, 10, 8))
    msg = run(planner.finalize_list(store, settings))
    text = store.get("plan", "draft")["orderText"]
    assert text.startswith("Shopping list for REWE – shopping Sat 10 Oct") and "Extras\n- Coffee" in text
    assert "is ready" in msg and "not approved yet" in store.get("plan", "current")["statusNote"]
    assert {st["group"] for st in store.list("staples")} == {"Pantry", "Oils, vinegar & sauces", "Spices", "Fridge & fresh"}


def test_english_skip_message_is_not_notified(store, settings, monkeypatch):
    monkeypatch.setattr(planner, "today", lambda s: date(2026, 10, 6))
    english(store)
    store.set("meals", "a", {"date": "2026-10-25", "kind": "cook", "title": "X"})
    msg = run(planner.draft_plan(store, settings))
    assert isinstance(msg, planner.Skip) and msg.startswith("The next plan isn't due until")


def test_ai_gets_english_instruction(store, settings, monkeypatch):
    english(store)
    settings.llm_provider = "claude"
    seen = {}

    async def fake(settings_, system, prompt, schema):
        seen["system"] = system
        return {"title": "Soup", "description": "", "serves": 2, "time": "20 min", "oven": "", "ingredients": ["1 l stock"],
                "steps": ["Heat."], "tip": "", "tags": []}

    monkeypatch.setattr(llm, "generate_json", fake)
    run(planner.recipe_generate(store, settings, "soup"))
    assert "OUTPUT LANGUAGE: Write all output text in English" in seen["system"]
    i18n.set_lang("de")
    run(planner.recipe_generate(store, settings, "Suppe"))
    assert "OUTPUT LANGUAGE" not in seen["system"]


def test_api_language_header_and_setting(settings):
    with TestClient(create_app(settings, run_scheduler=False)) as c:
        assert c.get("/api/config").json()["language"] == "de"
        r = c.post("/api/recipes/generate", json={"wish": "x"}, headers={"X-Lang": "en"})
        assert r.json()["detail"] == "This needs an AI (LLM_PROVIDER=claude or ollama)."
        c.put("/api/db/plan/settings", json={"language": "en"})
        assert c.get("/api/config").json()["language"] == "en"
        assert c.get("/api/db/nope").json()["detail"] == "Unknown collection"


def test_english_seed(settings):
    settings.language = "en"
    with TestClient(create_app(settings, run_scheduler=False)) as c:
        assert c.get("/api/config").json()["language"] == "en"
        assert c.get("/api/db/plan/current").json()["guidelines"].startswith("Two adults.")
