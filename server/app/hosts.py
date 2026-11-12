"""Two hosts, one container: the app on app.<domain> (ORIGIN) and the public website on <domain> (SITE_ORIGIN).

  host                       /                /<slug>                    app paths (/portal, /login, …)
  app.<domain>  (ORIGIN)     302 → /portal    308 → SITE_ORIGIN/<slug>   the app
  <domain> (+ SITE_HOSTS)    the website      website page or 404        308 → ORIGIN/<path>
  one host (no SITE_ORIGIN)  the website      website page or 404        the app

Server paths (/api, /mcp, /.well-known, /health, static files) answer on every host. Redirects are always built from
the configured addresses, never from the request's Host header. A host that is neither counts as the app.
"""

from typing import Literal
from urllib.parse import urlsplit

from fastapi import Request

from app import config

Surface = Literal["app", "site", "both"]


def _host(url: str) -> str:
    return urlsplit(url).netloc.lower()


def app_origin() -> str:
    return config.settings.origin.rstrip("/")


def site_origin() -> str:
    return config.settings.site_origin


def split() -> bool:
    """True when the website has its own host."""
    return _host(site_origin()) != _host(app_origin())


def surface(request: Request) -> Surface:
    if not split():
        return "both"
    host = (request.headers.get("host") or "").lower()
    if host == _host(site_origin()) or host.split(":")[0] in config.settings.site_hosts:
        return "site"
    return "app"


def app_link(path: str) -> str:
    """A link to an app page from a website page: relative on one host, absolute when the website has its own."""
    return app_origin() + path if split() else path


def site_link(path: str) -> str:
    """A link to a website page from the app (or a redirect to one)."""
    return site_origin() + path if split() else path


def site_url(path: str) -> str:
    """Absolute address of a website page, for canonical links, hreflang and og:url."""
    return site_origin() + path
