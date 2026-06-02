"""Thin MikroTik RouterOS REST helpers (httpx + HTTP Basic auth).

Endpoint form: ``http://<host>:<port>/rest/<menu-path>``. Two MikroTik
quirks are handled here:

* **Encoding.** Host-names/comments are passed through verbatim from DHCP
  clients; legacy Windows clients send cp1251. :func:`json_safe` cascades
  utf-8 -> cp1251 -> lossy replace so Cyrillic survives.
* **dict-or-list menus.** Single-object menus (``/system/identity`` etc.)
  sometimes return a dict, sometimes a one-item list. :func:`get_one`
  normalizes both.

httpx transport errors are mapped to :class:`MikrotError` so callers deal
only in errors-as-data.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from mikrot.errors import MikrotError
from mikrot.settings import Settings


def make_client(settings: Settings) -> httpx.Client:
    """Build a configured httpx client (caller closes it via ``with``)."""
    return httpx.Client(
        base_url=settings.base_url,
        auth=(settings.user, settings.password),
        timeout=settings.timeout,
        headers={"Accept": "application/json"},
    )


def json_safe(response: httpx.Response) -> Any:
    """Decode a response body tolerating mixed utf-8 / cp1251 content."""
    raw = response.content
    for codec in ("utf-8", "cp1251"):
        try:
            return json.loads(raw.decode(codec))
        except UnicodeDecodeError:
            continue
    return json.loads(raw.decode("utf-8", errors="replace"))


def request(client: httpx.Client, method: str, path: str, **kwargs: Any) -> httpx.Response:
    """Perform a request, raising :class:`MikrotError` on transport/HTTP errors.

    HTTP status errors map to ``http_error`` (exit 2); connect/timeout errors
    map to ``router_unreachable`` (exit 1).
    """
    try:
        response = client.request(method, path, **kwargs)
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        body = (exc.response.text or "").strip()
        raise MikrotError(
            f"HTTP {exc.response.status_code} on {exc.request.url}",
            code="http_error",
            fix_description=body[:500] or None,
            context={"status": exc.response.status_code},
        ) from exc
    except httpx.RequestError as exc:
        raise MikrotError(
            f"cannot reach router: {type(exc).__name__}: {exc}",
            code="router_unreachable",
            fix="mikrot doctor",
        ) from exc
    return response


def get_json(client: httpx.Client, path: str) -> Any:
    """GET ``path`` and return the decoded JSON body."""
    return json_safe(request(client, "GET", path))


def get_one(client: httpx.Client, path: str) -> dict[str, Any]:
    """GET a single-object menu, normalizing dict-or-list responses."""
    data = get_json(client, path)
    if isinstance(data, list):
        return data[0] if data else {}
    if isinstance(data, dict):
        return data
    return {"_raw": data}
