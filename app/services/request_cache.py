from __future__ import annotations

from typing import Any

from fastapi import Request


class RequestCache:
    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    def get(self, key: str) -> Any:
        return self._data.get(key)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value


def cache_key(*parts: object) -> str:
    return ":".join(str(part) for part in parts)


def get_request_cache(request: Request) -> RequestCache:
    cache = getattr(request.state, "request_cache", None)
    if cache is None:
        cache = RequestCache()
        request.state.request_cache = cache
    return cache
