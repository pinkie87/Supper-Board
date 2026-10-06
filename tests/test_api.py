import base64

from fastapi.testclient import TestClient

from app.main import create_app


def client(settings):
    return TestClient(create_app(settings, run_scheduler=False))


def test_crud_and_seed(settings):
    with client(settings) as c:
        assert c.get("/api/db/plan/current").json()["status"] == "active"
        assert len(c.get("/api/db/staples").json()) > 10
        new = c.post("/api/db/grocery", json={"text": "Milch"}).json()
        assert c.get(f"/api/db/grocery/{new['id']}").json() == {"text": "Milch"}
        assert c.patch(f"/api/db/grocery/{new['id']}", json={"text": "Hafermilch"}).status_code == 200
        assert c.patch("/api/db/grocery/fehlt", json={"text": "x"}).status_code == 404
        assert c.delete(f"/api/db/grocery/{new['id']}").status_code == 200
        assert c.get(f"/api/db/grocery/{new['id']}").status_code == 404
        assert c.get("/api/db/unbekannt").status_code == 404


def test_pages_and_config(settings):
    with client(settings) as c:
        page = c.get("/")
        assert page.status_code == 200 and '<html lang="de">' in page.text and "db.js" in page.text
        assert c.get("/db.js").status_code == 200
        cfg = c.get("/api/config").json()
        assert cfg["storeName"] == "REWE" and cfg["llm"] == "none" and cfg["shopWd"] == 5


def test_password(settings):
    settings.password = "geheim"
    with client(settings) as c:
        assert c.get("/api/health").status_code == 200
        assert c.get("/").status_code == 401
        token = base64.b64encode(b"egal:geheim").decode()
        assert c.get("/", headers={"Authorization": f"Basic {token}"}).status_code == 200
        bad = base64.b64encode(b"egal:falsch").decode()
        assert c.get("/api/db/meals", headers={"Authorization": f"Basic {bad}"}).status_code == 401


def test_ai_endpoints_need_provider(settings):
    with client(settings) as c:
        r = c.post("/api/recipes/generate", json={"wish": "Curry"})
        assert r.status_code == 400 and "KI" in r.json()["detail"]


def test_ha_today(settings):
    with client(settings) as c:
        data = c.get("/api/ha/today").json()
        assert data["tonight"] == "" and data["status"] == "active"
