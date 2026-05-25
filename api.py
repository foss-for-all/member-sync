from __future__ import annotations

import os
from typing import Any

import requests
import typer


class ApiError(RuntimeError):
    pass


def resolve_secret(value: str) -> str:
    if value.startswith("env:"):
        name = value.removeprefix("env:")
        secret = os.getenv(name)
        if secret is None:
            raise typer.BadParameter(f"environment variable {name!r} is not set")
        return secret
    return value


def request_json(
    session: requests.Session,
    method: str,
    url: str,
    *,
    expected_status: int | tuple[int, ...] = (200,),
    **kwargs: Any,
) -> Any:
    response = session.request(method, url, timeout=30, **kwargs)
    expected = (expected_status,) if isinstance(expected_status, int) else expected_status
    if response.status_code not in expected:
        detail = response.text.strip()
        raise ApiError(f"{method} {url} failed with HTTP {response.status_code}: {detail}")
    if response.status_code == 204 or not response.content:
        return None
    return response.json()


def paginated_get(
    session: requests.Session,
    url: str,
    *,
    items_key: str | None = None,
    page_size: int = 100,
    params: dict[str, Any] | None = None,
    pagination: str = "page",
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    page_size = min(max(page_size, 1), 100)
    base_params = dict(params or {})

    page = 1
    first = 0
    while True:
        page_params = dict(base_params)
        if pagination == "first":
            page_params.update({"first": first, "max": page_size})
        else:
            page_params.update({"page": page, "per_page": page_size})

        data = request_json(session, "GET", url, params=page_params)
        page_items = data[items_key] if items_key else data
        if not isinstance(page_items, list):
            raise ApiError(f"expected list response from {url}")

        items.extend(page_items)
        if len(page_items) < page_size:
            return items

        page += 1
        first += page_size


def normalize_base_url(url: str) -> str:
    return url.rstrip("/")
