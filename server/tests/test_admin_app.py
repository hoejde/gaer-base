"""The standalone admin app: /admin/* gets web/dist/admin.html, the app's routes index.html, the rest is the website."""

from dataclasses import replace

import httpx

from app import config
from app.main import create_app
from tests.helpers import full_user


async def test_admin_paths_serve_admin_html(tmp_path, monkeypatch):
    (tmp_path / "index.html").write_text("APP")
    (tmp_path / "admin.html").write_text("ADMIN")
    (tmp_path / "assets").mkdir()
    monkeypatch.setattr(config, "settings", replace(config.settings, static_dir=str(tmp_path)))
    app = create_app()
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost", headers={"x-gaer": "1"})

    for path in ("/admin", "/admin/", "/admin/users", "/admin/app-stores/tekster"):
        r = await client.get(path)
        assert r.status_code == 200 and r.text == "ADMIN", path
    for path in ("/klip", "/portal", "/m/klip"):
        assert (await client.get(path)).text == "APP", path
    for path in ("/", "/administration"):  # one host: the website answers / and anything that is not the app's
        r = await client.get(path)
        assert "APP" not in r.text and "<html" in r.text, path
    assert (await client.get("/administration")).status_code == 404

    await full_user(client, "11111111")
    assert "<html" in (await client.get("/")).text  # signed in or not, / is the website
    assert (await client.get("/portal")).text == "APP"


async def test_analytics_has_user_and_login_numbers(make_client):
    admin = make_client()
    await full_user(admin, "11111111")  # one grace login, then a passkey
    other = make_client()
    r = await other.post("/api/auth/otp/start", json={"phone": "22222222"})
    await other.post("/api/auth/otp/verify", json={"phone": "22222222", "code": "000000" if r.json()["dev_code"] != "000000" else "111111"})

    data = (await admin.get("/api/admin/analytics?days=7")).json()
    assert data["users"] == {"total": 1, "new": 1, "active": 1, "with_passkey": 1, "must_passkey": 0}
    assert data["logins"]["otp"] == 1 and data["logins"]["passkey"] == 0
    assert data["logins"]["failed"] == 1 and data["logins"]["failed_24h"] == 1
    assert sum(d["logins"] for d in data["logins_per_day"]) == 1
