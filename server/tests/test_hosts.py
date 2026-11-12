"""Two hosts, one container (app/hosts.py): the app on app.<domain> (ORIGIN), the website on <domain> (SITE_ORIGIN)."""

from dataclasses import replace

import httpx
import pytest

from app import config, hosts
from app.main import create_app

APP, SITE, EXTRA = "app.kunde.dk", "kunde.dk", "kunde.eu"


@pytest.fixture
def split(tmp_path, monkeypatch):
    (tmp_path / "index.html").write_text("APP")
    (tmp_path / "admin.html").write_text("ADMIN")
    (tmp_path / "favicon.svg").write_text("<svg/>")
    monkeypatch.setattr(config, "settings", replace(
        config.settings, static_dir=str(tmp_path), origin=f"https://{APP}", site_origin_env=f"https://{SITE}",
        site_hosts_env=f" {EXTRA} ,www.{SITE}"))
    transport = httpx.ASGITransport(app=create_app())

    def on(host: str) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=transport, base_url=f"http://{host}", headers={"x-gaer": "1"})
    return on


async def test_app_host_sends_the_website_across(split):
    app = split(APP)
    r = await app.get("/")
    assert r.status_code == 302 and r.headers["location"] == "/portal"
    assert (await app.get("/?utm=x")).headers["location"] == "/portal?utm=x"
    for path in ("/portal", "/login", "/klip/7", "/privatliv", "/m/klip"):
        r = await app.get(path)
        assert r.status_code == 200 and r.text == "APP", path
    assert (await app.get("/admin/users")).text == "ADMIN"
    r = await app.get("/om?lang=en")
    assert r.status_code == 308 and r.headers["location"] == f"https://{SITE}/om?lang=en"
    r = await app.get("/w/om")  # the old address goes straight to the website's host
    assert r.status_code == 308 and r.headers["location"] == f"https://{SITE}/om"
    assert (await app.get("/api/public/config")).json()["site_url"] == f"https://{SITE}/"


async def test_site_host_shows_the_website_and_sends_the_app_across(split):
    for host in (SITE, EXTRA, f"www.{SITE}"):
        site = split(host)
        r = await site.get("/")
        assert r.status_code == 200 and 'class="login-card"' in r.text, host
        assert f'<link rel="canonical" href="https://{SITE}/?lang=da">' in r.text  # canonical is SITE_ORIGIN
        assert f'href="https://{APP}/login"' in r.text and f'href="https://{APP}/privatliv"' in r.text
        assert (await site.get("/findes-ikke")).status_code == 404
        for path in ("/portal", "/login?next=/klip", "/admin/users", "/m"):
            r = await site.get(path)
            assert r.status_code == 308 and r.headers["location"] == f"https://{APP}{path}", (host, path)
        # Shared by both: static files, the API the website calls, the website's own CSS/JS, health.
        assert (await site.get("/favicon.svg")).text == "<svg/>"
        assert (await site.get("/api/public/config")).status_code == 200
        assert (await site.get("/static/w/w.css")).status_code == 200
        assert (await site.get("/health")).status_code == 200


async def test_redirects_never_follow_the_host_header(split):
    stranger = split("evil.example")  # neither host: treated as the app
    assert (await stranger.get("/")).headers["location"] == "/portal"
    assert (await stranger.get("/om")).headers["location"] == f"https://{SITE}/om"
    assert (await split(SITE).get("/login")).headers["location"] == f"https://{APP}/login"
    assert (await split(f"{SITE}.evil.example").get("/om")).headers["location"].startswith(f"https://{SITE}/")


def test_one_host_without_site_origin(monkeypatch):
    monkeypatch.setattr(config, "settings", replace(config.settings, origin="https://app.kunde.dk", site_origin_env=None))
    assert not hosts.split() and hosts.site_origin() == "https://app.kunde.dk"
    assert hosts.app_link("/login") == "/login" and hosts.site_link("/om") == "/om"
    assert hosts.site_url("/om") == "https://app.kunde.dk/om"
    monkeypatch.setattr(config, "settings", replace(config.settings, site_origin_env="https://kunde.dk/"))
    assert hosts.split() and hosts.site_link("/") == "https://kunde.dk/" and hosts.app_link("/login") == "https://app.kunde.dk/login"
