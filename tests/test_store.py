import pytest

from app.store import NotFound, merge, split_path


def test_set_get_list(store):
    store.set("grocery", "a", {"text": "Milch"})
    store.set("grocery", "b", {"text": "Eier"})
    assert store.get("grocery", "a") == {"text": "Milch"}
    assert [d["text"] for d in store.list("grocery")] == ["Milch", "Eier"]
    assert store.list("grocery")[0]["id"] == "a"


def test_update_merges_and_deletes_fields(store):
    store.set("plan", "current", {"status": "active", "pickup": "Sa.", "meta": {"a": 1, "b": 2}})
    store.update("plan", "current", {"status": "drafted", "pickup": {"__delete__": True}, "meta": {"b": 3}})
    assert store.get("plan", "current") == {"status": "drafted", "meta": {"a": 1, "b": 3}}


def test_update_missing_raises(store):
    with pytest.raises(NotFound):
        store.update("meals", "nope", {"x": 1})


def test_set_strips_client_fields(store):
    store.set("meals", "x", {"id": "x", "_col": "meals", "title": "Suppe"})
    assert store.get("meals", "x") == {"title": "Suppe"}


def test_split_path_rejects_unknown():
    assert split_path("meals/abc") == ("meals", "abc")
    with pytest.raises(ValueError):
        split_path("users/abc")


def test_merge_copies_values():
    src = {"list": [1, 2]}
    target = merge({}, src)
    src["list"].append(3)
    assert target["list"] == [1, 2]
