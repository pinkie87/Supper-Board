"""Supper Board – Webserver."""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import secrets
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse

from . import i18n, llm, notify, planner, recipes, scheduler
from .config import Settings, settings as default_settings
from .i18n import T
from .seed import seed
from .store import COLLECTIONS, NotFound, Store

log = logging.getLogger("supper_board")
WEB = Path(__file__).resolve().parent.parent / "web"


def create_app(settings: Settings | None = None, run_scheduler: bool = True) -> FastAPI:
    settings = settings or default_settings
    i18n.set_default(settings.language)
    store = Store(settings.db_path)
    seed(store, settings.language)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        store.attach_loop(asyncio.get_running_loop())
        task = asyncio.create_task(scheduler.run(store, settings)) if run_scheduler else None
        yield
        if task:
            task.cancel()
        store.close()

    app = FastAPI(title="Supper Board", lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.store = store
    app.state.settings = settings
    background: set[asyncio.Task] = set()

    # ---------- Sprache und Passwortschutz ----------
    @app.middleware("http")
    async def auth(request: Request, call_next):
        # Das Board schickt seine Sprache mit; sonst gilt die Einstellung des Haushalts.
        wanted = request.headers.get("x-lang", "")
        i18n.set_lang(wanted if wanted in i18n.LANGUAGES else i18n.household_lang(store))
        if settings.password and request.url.path != "/api/health":
            ok = False
            header = request.headers.get("authorization", "")
            if header.lower().startswith("basic "):
                try:
                    _, _, pw = base64.b64decode(header[6:]).decode().partition(":")
                    ok = secrets.compare_digest(pw.encode(), settings.password.encode())
                except Exception:  # noqa: BLE001
                    ok = False
            if not ok:
                return Response(T("Anmeldung erforderlich", "Login required"), status_code=401,
                                headers={"WWW-Authenticate": 'Basic realm="Supper Board", charset="UTF-8"'})
        return await call_next(request)

    def col_or_404(col: str) -> str:
        if col not in COLLECTIONS:
            raise HTTPException(404, T("Unbekannte Sammlung", "Unknown collection"))
        return col

    # ---------- Seite ----------
    @app.get("/", include_in_schema=False)
    async def index():
        return FileResponse(WEB / "index.html", headers={"Cache-Control": "no-cache"})

    @app.get("/db.js", include_in_schema=False)
    async def dbjs():
        return FileResponse(WEB / "db.js", media_type="text/javascript", headers={"Cache-Control": "no-cache"})

    @app.get("/manifest.webmanifest", include_in_schema=False)
    async def manifest():
        return FileResponse(WEB / "manifest.webmanifest", media_type="application/manifest+json")

    @app.get("/icon.svg", include_in_schema=False)
    async def icon():
        return FileResponse(WEB / "icon.svg", media_type="image/svg+xml")

    @app.get("/api/health")
    async def health():
        return {"ok": True}

    @app.get("/api/config")
    async def config():
        return {
            "storeName": settings.store_name, "storeUrl": settings.store_url, "storeSearchUrl": settings.store_search_url,
            "llm": settings.llm_provider if settings.llm_enabled else "none",
            "llmLabel": {"claude": "Claude", "ollama": "Ollama"}.get(settings.llm_provider, ""),
            "notify": notify.enabled(settings),
            "draftDay": planner.wd_long(settings.draft_weekday), "listDay": planner.wd_long(settings.list_weekday),
            "shopDay": planner.wd_long(settings.shop_weekday),
            "language": i18n.household_lang(store),
            "draftWd": settings.draft_weekday, "listWd": settings.list_weekday, "shopWd": settings.shop_weekday,
        }

    # ---------- Datenbank ----------
    @app.get("/api/db/{col}")
    async def list_docs(col: str):
        return store.list(col_or_404(col))

    @app.post("/api/db/{col}")
    async def add_doc(col: str, data: dict[str, Any] = Body(...)):
        return {"id": store.add(col_or_404(col), data)}

    @app.get("/api/db/{col}/{doc_id}")
    async def get_doc(col: str, doc_id: str, missing: str = ""):
        doc = store.get(col_or_404(col), doc_id)
        if doc is None:
            if missing == "null":  # Live-Abos fragen auch nach Dokumenten, die es (noch) nicht gibt
                return None
            raise HTTPException(404, T("Nicht gefunden", "Not found"))
        return doc

    @app.put("/api/db/{col}/{doc_id}")
    async def set_doc(col: str, doc_id: str, data: dict[str, Any] = Body(...)):
        store.set(col_or_404(col), doc_id, data)
        return {"ok": True}

    @app.patch("/api/db/{col}/{doc_id}")
    async def update_doc(col: str, doc_id: str, data: dict[str, Any] = Body(...)):
        try:
            store.update(col_or_404(col), doc_id, data)
        except NotFound:
            raise HTTPException(404, T("Nicht gefunden", "Not found"))
        return {"ok": True}

    @app.delete("/api/db/{col}/{doc_id}")
    async def delete_doc(col: str, doc_id: str):
        store.delete(col_or_404(col), doc_id)
        return {"ok": True}

    @app.get("/api/events")
    async def events(request: Request):
        q = store.subscribe()

        async def stream():
            try:
                yield "retry: 3000\n\n"
                while True:
                    try:
                        event = await asyncio.wait_for(q.get(), timeout=25)
                        yield f"data: {json.dumps(event)}\n\n"
                    except asyncio.TimeoutError:
                        yield ": ping\n\n"
                    if await request.is_disconnected():
                        break
            finally:
                store.unsubscribe(q)

        return StreamingResponse(stream(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    # ---------- Aktionen ----------
    def start_job(name: str, fn) -> JSONResponse:
        if planner._job_lock.locked():
            return JSONResponse({"ok": False, "message": T("Es läuft schon eine Aufgabe.", "A job is already running.")}, status_code=409)
        task = asyncio.create_task(planner.run_job(store, settings, name, fn))
        background.add(task)
        task.add_done_callback(background.discard)
        return JSONResponse({"ok": True})

    @app.post("/api/actions/draft")
    async def action_draft():
        return start_job("draft", lambda: planner.draft_plan(store, settings, force=True))

    @app.post("/api/actions/list")
    async def action_list():
        return start_job("list", lambda: planner.finalize_list(store, settings, force=True))

    @app.post("/api/actions/discard-draft")
    async def action_discard_draft():
        for m in store.list("draft"):
            store.delete("draft", m["id"])
        store.delete("plan", "draft")
        cur = store.get("plan", "current") or {}
        cur.update(status="active")
        cur.pop("pickup", None)
        cur.pop("statusNote", None)
        store.set("plan", "current", cur)
        return {"ok": True}

    @app.post("/api/actions/notify-test")
    async def action_notify_test():
        if not notify.enabled(settings):
            raise HTTPException(400, T("Home Assistant ist nicht eingerichtet (HA_URL, HA_TOKEN, HA_NOTIFY).",
                                      "Home Assistant is not set up (HA_URL, HA_TOKEN, HA_NOTIFY)."))
        ok = await notify.send(settings, "Supper Board", T("Testnachricht – Benachrichtigungen funktionieren.", "Test message – notifications work."))
        if not ok:
            raise HTTPException(502, T("Home Assistant hat die Nachricht nicht angenommen. Details im Server-Log.",
                                      "Home Assistant did not accept the message. See the server log for details."))
        return {"ok": True}

    @app.post("/api/meals/{col}/{doc_id}/save-recipe")
    async def save_recipe(col: str, doc_id: str):
        if col not in ("meals", "draft", "history"):
            raise HTTPException(404)
        meal = store.get(col, doc_id)
        if not meal or not meal.get("recipe"):
            raise HTTPException(404, T("Dieses Gericht hat kein Rezept.", "This meal has no recipe."))
        rid = planner.save_meal_as_recipe(store, meal)
        store.update(col, doc_id, {"recipeId": rid})
        return {"id": rid}

    # ---------- Rezepte ----------
    def llm_or_400():
        if not settings.llm_enabled:
            raise HTTPException(400, T("Dafür ist eine KI nötig (LLM_PROVIDER=claude oder ollama).", "This needs an AI (LLM_PROVIDER=claude or ollama)."))

    async def llm_call(coro):
        try:
            return await coro
        except llm.LLMError as e:
            raise HTTPException(502, str(e))

    @app.post("/api/recipes/import-url")
    async def import_url(body: dict[str, str] = Body(...)):
        url = (body.get("url") or "").strip()
        try:
            page = await recipes.fetch_page(url)
        except recipes.ImportError_ as e:
            raise HTTPException(400, str(e))
        recipe = recipes.parse_jsonld(page)
        if recipe and recipes.needs_metric(recipe) and settings.llm_enabled:
            recipe = await llm_call(planner.recipe_from_text(settings, json.dumps(recipe, ensure_ascii=False)))
        if not recipe:
            if not settings.llm_enabled:
                raise HTTPException(400, T("Auf dieser Seite wurden keine Rezeptdaten gefunden.", "No recipe data was found on this page."))
            recipe = await llm_call(planner.recipe_from_text(settings, recipes.page_text(page)))
        recipe["source"] = url
        return recipe

    @app.post("/api/recipes/from-text")
    async def from_text(body: dict[str, str] = Body(...)):
        llm_or_400()
        text = (body.get("text") or "").strip()
        if len(text) < 20:
            raise HTTPException(400, T("Bitte den Rezepttext einfügen.", "Please paste the recipe text."))
        recipe = await llm_call(planner.recipe_from_text(settings, text))
        recipe["source"] = T("Text (KI)", "Text (AI)")
        return recipe

    @app.post("/api/recipes/generate")
    async def generate(body: dict[str, str] = Body(...)):
        llm_or_400()
        wish = (body.get("wish") or "").strip()
        if not wish:
            raise HTTPException(400, T("Bitte beschreiben, was für ein Rezept es sein soll.", "Please describe what kind of recipe you want."))
        recipe = await llm_call(planner.recipe_generate(store, settings, wish))
        recipe["source"] = T(f"KI ({settings.llm_provider})", f"AI ({settings.llm_provider})")
        return recipe

    # ---------- Home Assistant: Sensor-Daten ----------
    @app.get("/api/ha/today")
    async def ha_today():
        t = planner.today(settings)
        meals = {m["date"]: m for m in store.list("meals") + store.list("draft")}
        tonight = meals.get(t.isoformat())
        tomorrow = meals.get((t + timedelta(days=1)).isoformat())
        cur = store.get("plan", "current") or {}
        return {
            "tonight": tonight["title"] if tonight else "",
            "tonight_kind": tonight["kind"] if tonight else "",
            "tomorrow": tomorrow["title"] if tomorrow else "",
            "thaw_tonight": tomorrow.get("thaw", "") if tomorrow and not tomorrow.get("thawDone") else "",
            "status": cur.get("status", "active"),
            "next_order_items": len(store.list("grocery")) + sum(1 for s in store.list("staples") if s.get("status") == "low"),
        }

    return app
