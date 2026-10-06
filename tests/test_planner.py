import asyncio
from datetime import date, timedelta

import pytest

from app import llm, planner
from app.seed import seed


def run(coro):
    return asyncio.run(coro)


def fixed_today(monkeypatch, d: date):
    monkeypatch.setattr(planner, "today", lambda settings: d)


def add_recipes(store, n=4):
    ids = []
    for i in range(n):
        ids.append(store.add("recipes", {"title": f"Gericht {i}", "description": "", "serves": 2, "time": "30 Min.",
                                         "oven": "", "ingredients": [f"{i * 100} g Zutat {i}"], "steps": ["Kochen."],
                                         "tip": "", "tags": []}))
    return ids


def test_cycle_uses_shop_day_and_plan_end(store, settings, monkeypatch):
    fixed_today(monkeypatch, date(2026, 10, 6))  # Dienstag
    store.set("meals", "a", {"date": "2026-10-11", "kind": "cook", "title": "X"})  # Sonntag
    c = planner.cycle(store, settings)
    assert c["start"] == date(2026, 10, 12)  # Montag
    assert c["shop"] == date(2026, 10, 10)  # Samstag davor
    assert c["end"] == date(2026, 10, 25)


def test_cycle_first_plan_starts_next_monday(store, settings, monkeypatch):
    fixed_today(monkeypatch, date(2026, 10, 6))
    c = planner.cycle(store, settings)
    assert c["start"] == date(2026, 10, 12)
    assert c["shop"] == date(2026, 10, 10)


def test_draft_not_due_without_force(store, settings, monkeypatch):
    fixed_today(monkeypatch, date(2026, 10, 6))
    store.set("meals", "a", {"date": "2026-10-25", "kind": "cook", "title": "X"})
    msg = run(planner.draft_plan(store, settings))
    assert "erst ab" in msg
    assert store.list("draft") == []


def test_draft_from_db_without_ai(store, settings, monkeypatch):
    fixed_today(monkeypatch, date(2026, 10, 6))
    seed(store)
    add_recipes(store)
    msg = run(planner.draft_plan(store, settings, force=True))
    draft = sorted(store.list("draft"), key=lambda m: m["date"])
    assert draft[0]["date"] == "2026-10-12" and draft[-1]["date"] == "2026-10-25"
    assert {m["kind"] for m in draft} == {"cook", "leftovers", "flex"}
    cook = [m for m in draft if m["kind"] == "cook"]
    assert len(cook) == 6 and all(m["recipeId"] and m["recipe"]["ingredients"] for m in cook)
    leftovers = [m for m in draft if m["kind"] == "leftovers"]
    assert all(m["from"].startswith("p20261012-") for m in leftovers)
    assert store.get("plan", "current")["status"] == "drafted"
    assert store.get("plan", "draft")["pickup"] == "Sa. 10.10."
    assert "Neuer Speiseplan 12.10.–25.10." in msg


def test_draft_without_recipes_or_ai_fails(store, settings, monkeypatch):
    fixed_today(monkeypatch, date(2026, 10, 6))
    seed(store)
    with pytest.raises(planner.PlanError):
        run(planner.draft_plan(store, settings, force=True))


def test_draft_with_ai(store, settings, monkeypatch):
    fixed_today(monkeypatch, date(2026, 10, 6))
    seed(store)
    rid = add_recipes(store, 1)[0]
    settings.llm_provider = "claude"
    seen = {}

    async def fake(settings_, system, prompt, schema):
        seen["prompt"] = prompt
        recipe = {"title": "", "description": "", "serves": 4, "time": "40 Min.", "oven": "200 °C Umluft",
                  "ingredients": ["500 g Hähnchenbrust"], "steps": ["Garen bis 74 °C."], "tip": "", "tags": []}
        empty = {k: ([] if isinstance(v, list) else "" if isinstance(v, str) else 0) for k, v in recipe.items()}
        return {
            "summary": "Neu: Hähnchen.", "prep": "Bei Ankunft einfrieren: Lachs.",
            "meals": [
                {"date": "2026-10-12", "kind": "cook", "title": "Hähnchen", "details": "", "thaw": "", "recipeId": "", "fromDate": "", "recipe": recipe},
                {"date": "2026-10-13", "kind": "leftovers", "title": "Reste: Hähnchen", "details": "", "thaw": "", "recipeId": "", "fromDate": "2026-10-12", "recipe": empty},
                {"date": "2026-10-19", "kind": "cook", "title": "Aus der DB", "details": "", "thaw": "der Lachs (ca. 400 g)", "recipeId": rid, "fromDate": "", "recipe": empty},
                {"date": "2030-01-01", "kind": "cook", "title": "Außerhalb", "details": "", "thaw": "", "recipeId": "", "fromDate": "", "recipe": recipe},
            ],
            "groceries": [{"section": "Obst & Gemüse", "items": ["1 Zucchini"]}, {"section": "Leer", "items": []}],
        }

    monkeypatch.setattr(llm, "generate_json", fake)
    run(planner.draft_plan(store, settings, force=True))
    assert "Gericht 0" in seen["prompt"] and "REZEPTDATENBANK" in seen["prompt"]
    draft = {m["date"]: m for m in store.list("draft")}
    assert set(draft) == {"2026-10-12", "2026-10-13", "2026-10-19"}
    assert draft["2026-10-13"]["from"] == "p20261012-01"
    assert "recipe" not in draft["2026-10-13"]
    assert draft["2026-10-19"]["recipeId"] == rid and draft["2026-10-19"]["recipe"]["ingredients"] == ["0 g Zutat 0"]
    assert draft["2026-10-19"]["thaw"] == "der Lachs (ca. 400 g)"
    assert store.get("plan", "draft")["groceries"] == [{"section": "Obst & Gemüse", "items": ["1 Zucchini"]}]


def test_finalize_list_merges_extras(store, settings, monkeypatch):
    fixed_today(monkeypatch, date(2026, 10, 6))
    seed(store)
    add_recipes(store)
    run(planner.draft_plan(store, settings, force=True))
    store.add("grocery", {"text": "Kaffee", "at": "2026-10-06T10:00"})
    staple = store.list("staples")[0]
    store.update("staples", staple["id"], {"status": "low"})
    fixed_today(monkeypatch, date(2026, 10, 8))
    msg = run(planner.finalize_list(store, settings))
    d = store.get("plan", "draft")
    assert "Einkaufsliste für REWE – Einkauf Sa. 10.10." in d["orderText"]
    assert "- Kaffee" in d["orderText"] and f"- {staple['name']}" in d["orderText"]
    assert len(d["included"]["grocery"]) == 1 and d["included"]["staples"] == [staple["id"]]
    cur = store.get("plan", "current")
    assert cur["status"] == "list_ready" and "noch nicht freigegeben" in cur["statusNote"]
    assert "ist fertig" in msg


def test_finalize_replaces_swapped_meals_without_ai(store, settings, monkeypatch):
    fixed_today(monkeypatch, date(2026, 10, 6))
    seed(store)
    add_recipes(store, 8)
    run(planner.draft_plan(store, settings, force=True))
    first = sorted((m for m in store.list("draft") if m["kind"] == "cook"), key=lambda m: m["date"])[0]
    store.update("draft", first["id"], {"swapOut": True})
    run(planner.finalize_list(store, settings, force=True))
    after = store.get("draft", first["id"])
    assert after["swapOut"] is False and after["recipeId"] != first["recipeId"]


def test_housekeeping_promotes_draft_and_saves_good_recipes(store, settings, monkeypatch):
    fixed_today(monkeypatch, date(2026, 10, 12))
    seed(store)
    store.set("meals", "old1", {"date": "2026-10-09", "kind": "cook", "title": "Lecker", "rating": 5,
                                "recipe": {"serves": 2, "ingredients": ["x"], "steps": ["y"]}})
    store.set("draft", "p1", {"date": "2026-10-12", "kind": "cook", "title": "Neu", "swapOut": False})
    store.set("plan", "draft", {"start": "2026-10-12"})
    assert planner.housekeeping(store, settings)
    assert [m["id"] for m in store.list("meals")] == ["p1"]
    hist = store.get("history", "old1")
    assert hist["recipeId"] and store.get("recipes", hist["recipeId"])["title"] == "Lecker"
    assert store.get("plan", "draft") is None
    assert store.get("plan", "current")["status"] == "active"


def test_run_job_reports_errors(store, settings):
    async def boom():
        raise planner.PlanError("kaputt")

    msg = run(planner.run_job(store, settings, "draft", boom))
    assert msg == "kaputt"
    assert store.get("plan", "job")["state"] == "error"
