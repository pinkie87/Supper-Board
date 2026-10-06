import asyncio
import base64
import json
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from app import llm, photos
from app.main import create_app

# 1×1-Pixel-PNG
PNG = "data:image/png;base64," + base64.b64encode(
    bytes.fromhex("89504e470d0a1a0a0000000d4948445200000001000000010806000000"
                  "1f15c4890000000d49444154789c6360000002000100e221bc330000000049454e44ae426082")).decode()

RECIPE = {"title": "Apfelkuchen", "description": "", "serves": 12, "time": "", "oven": "180 °C Umluft",
          "ingredients": ["500 g Äpfel", "200 g Mehl"], "steps": ["Backen."], "tip": "Oma: mehr Zimt", "tags": ["Kuchen"]}


def wait_for(fn, timeout=5.0):
    end = time.time() + timeout
    while time.time() < end:
        if fn():
            return True
        time.sleep(0.05)
    return False


def test_parse_json_tolerates_local_model_output():
    assert llm.parse_json('<think>hm</think>```json\n{"a": 1}\n```') == {"a": 1}
    assert llm.parse_json('Hier ist das Ergebnis: {"a": 2} – fertig') == {"a": 2}
    with pytest.raises(json.JSONDecodeError):
        llm.parse_json("kein json")


def test_decode_image_rejects_bad_input():
    with pytest.raises(photos.PhotoError):
        photos.decode_image("data:text/plain;base64,aGFsbG8=")
    with pytest.raises(photos.PhotoError):
        photos.decode_image("data:image/png;base64,!!!")
    assert photos.decode_image(PNG)[0] == "image/png"


def test_photo_import_end_to_end(settings, monkeypatch):
    settings.llm_provider = "ollama"
    calls = []

    async def fake(settings_, system, prompt, schema, images=None):
        calls.append((prompt, images))
        if len(calls) == 1:
            return {"recipes": [RECIPE, {**RECIPE, "title": "Leer", "ingredients": [], "steps": []}]}
        raise llm.LLMError("Ollama nicht erreichbar")

    monkeypatch.setattr(llm, "generate_json", fake)
    with TestClient(create_app(settings, run_scheduler=False)) as c:
        r = c.post("/api/imports", json={"images": [PNG, PNG], "together": False})
        assert r.status_code == 200 and len(r.json()["ids"]) == 2
        first, second = r.json()["ids"]
        assert wait_for(lambda: c.get(f"/api/db/imports/{second}").json().get("state") == "error")
        doc = c.get(f"/api/db/imports/{first}").json()
        assert doc["state"] == "done" and [x["title"] for x in doc["recipes"]] == ["Apfelkuchen"]
        assert doc["recipes"][0]["source"] == "Foto"
        assert "Ollama nicht erreichbar" in c.get(f"/api/db/imports/{second}").json()["message"]
        mime, data = calls[0][1][0]
        assert mime == "image/png" and base64.b64decode(data)[:4] == b"\x89PNG"
        assert c.get(f"/api/imports/{first}/image/0").status_code == 200
        assert c.get(f"/api/imports/{first}/image/5").status_code == 404
        # erneut versuchen
        async def ok(settings_, system, prompt, schema, images=None):
            return {"recipes": [RECIPE]}
        monkeypatch.setattr(llm, "generate_json", ok)
        assert c.post(f"/api/imports/{second}/retry").status_code == 200
        assert wait_for(lambda: c.get(f"/api/db/imports/{second}").json().get("state") == "done")
        # löschen entfernt Dokument und Bild
        files = list((settings.data_dir / "uploads").iterdir())
        assert len(files) == 2
        assert c.delete(f"/api/imports/{first}").status_code == 200
        assert c.get(f"/api/db/imports/{first}").status_code == 404
        assert len(list((settings.data_dir / "uploads").iterdir())) == 1


def test_photos_together_make_one_job(settings, monkeypatch):
    settings.llm_provider = "ollama"
    seen = []

    async def fake(settings_, system, prompt, schema, images=None):
        seen.append(len(images))
        return {"recipes": [RECIPE]}

    monkeypatch.setattr(llm, "generate_json", fake)
    with TestClient(create_app(settings, run_scheduler=False)) as c:
        ids = c.post("/api/imports", json={"images": [PNG, PNG, PNG], "together": True}).json()["ids"]
        assert len(ids) == 1
        assert wait_for(lambda: c.get(f"/api/db/imports/{ids[0]}").json().get("state") == "done")
        assert seen == [3]


def test_photo_import_needs_ai(settings):
    with TestClient(create_app(settings, run_scheduler=False)) as c:
        assert c.post("/api/imports", json={"images": [PNG]}).status_code == 400


def test_ollama_sends_images_to_vision_model(settings, monkeypatch):
    settings.llm_provider, settings.ollama_model, settings.ollama_vision_model = "ollama", "qwen3:14b", "qwen2.5vl:7b"
    sent = {}

    async def post(self, url, json=None, **kw):
        sent.update(url=url, body=json)
        return httpx.Response(200, json={"message": {"content": '{"recipes": []}'}})

    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    asyncio.run(llm.generate_json(settings, "sys", "prompt", photos.PHOTO_SCHEMA, images=[("image/png", "QUJD")]))
    assert sent["body"]["model"] == "qwen2.5vl:7b"
    assert sent["body"]["messages"][1]["images"] == ["QUJD"]
    asyncio.run(llm.generate_json(settings, "sys", "prompt", photos.PHOTO_SCHEMA))
    assert sent["body"]["model"] == "qwen3:14b" and "images" not in sent["body"]["messages"][1]


def test_openai_compatible_server(settings, monkeypatch):
    settings.llm_provider, settings.openai_url, settings.openai_vision_model = "openai", "http://pc:8080/v1", "vision"
    requests = []

    async def post(self, url, json=None, **kw):
        requests.append(dict(json))
        if "response_format" in json:  # Server ohne JSON-Schema-Unterstützung
            return httpx.Response(400, text="unsupported response_format")
        return httpx.Response(200, json={"choices": [{"message": {"content": '```json\n{"recipes": []}\n```'}}]})

    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    out = asyncio.run(llm.generate_json(settings, "sys", "prompt", photos.PHOTO_SCHEMA, images=[("image/jpeg", "QUJD")]))
    assert out == {"recipes": []}
    assert len(requests) == 2 and requests[1]["model"] == "vision"
    part = requests[1]["messages"][1]["content"][0]
    assert part == {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,QUJD"}}


def test_unreachable_local_ai_gives_clear_error(settings, monkeypatch):
    settings.llm_provider = "openai"

    async def post(self, url, json=None, **kw):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    with pytest.raises(llm.LLMError, match="Läuft der PC"):
        asyncio.run(llm.generate_json(settings, "sys", "prompt", {}))


def test_provider_labels(settings):
    settings.llm_provider = "openai"
    settings.openai_url = "https://openrouter.ai/api/v1"
    assert llm.provider_label(settings) == "OpenRouter" and llm.is_cloud(settings)
    settings.openai_url = "https://generativelanguage.googleapis.com/v1beta/openai"
    assert llm.provider_label(settings) == "Gemini"
    settings.openai_url = "http://192.168.178.20:8080/v1"
    assert llm.provider_label(settings) == "Lokale KI" and not llm.is_cloud(settings)


def test_openrouter_headers_and_rate_limit(settings, monkeypatch):
    settings.llm_provider, settings.openai_url, settings.openai_api_key = "openai", "https://openrouter.ai/api/v1", "sk-or-test"
    seen = {}

    class FakeClient(httpx.AsyncClient):
        def __init__(self, *a, headers=None, **kw):
            seen["headers"] = dict(headers or {})
            super().__init__(*a, **kw)

        async def post(self, url, json=None, **kw):
            seen["url"] = url
            return httpx.Response(429, headers={"Retry-After": "120"}, text="rate limited")

    monkeypatch.setattr(llm.httpx, "AsyncClient", FakeClient)
    with pytest.raises(llm.LLMRateLimited) as err:
        asyncio.run(llm.generate_json(settings, "sys", "prompt", {}))
    assert err.value.retry_after == 120 and "OpenRouter: Limit erreicht" in str(err.value)
    assert seen["url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert seen["headers"]["Authorization"] == "Bearer sk-or-test" and seen["headers"]["X-Title"] == "Supper Board"


def test_photo_import_pauses_on_rate_limit(settings, monkeypatch):
    settings.llm_provider = "openai"
    settings.openai_url = "https://generativelanguage.googleapis.com/v1beta/openai"
    calls = []

    async def limited(settings_, system, prompt, schema, images=None):
        calls.append(1)
        raise llm.LLMRateLimited("Gemini: Limit erreicht.", 30)

    monkeypatch.setattr(llm, "generate_json", limited)
    with TestClient(create_app(settings, run_scheduler=False)) as c:
        first, second = c.post("/api/imports", json={"images": [PNG, PNG]}).json()["ids"]
        assert wait_for(lambda: c.get(f"/api/db/imports/{first}").json().get("retryAt"))
        doc = c.get(f"/api/db/imports/{first}").json()
        assert doc["state"] == "waiting" and doc["attempts"] == 1 and "Neuer Versuch automatisch um" in doc["message"]
        time.sleep(0.3)
        assert len(calls) == 1  # Warteschlange pausiert, das zweite Foto wartet
        assert c.get(f"/api/db/imports/{second}").json()["state"] == "waiting"

        async def ok(settings_, system, prompt, schema, images=None):
            return {"recipes": [RECIPE]}

        monkeypatch.setattr(llm, "generate_json", ok)
        assert c.post(f"/api/imports/{first}/retry").status_code == 200  # sofort erneut versuchen
        assert wait_for(lambda: c.get(f"/api/db/imports/{first}").json().get("state") == "done")
        done = c.get(f"/api/db/imports/{first}").json()
        assert "retryAt" not in done and "attempts" not in done
