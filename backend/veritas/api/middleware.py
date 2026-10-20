"""Attach one correlation id to each HTTP request and its response."""

from __future__ import annotations

import re
from uuid import uuid4

from starlette.types import ASGIApp, Message, Receive, Scope, Send

_SAFE_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
_HEADER = b"x-request-id"


def resolve_correlation_id(raw_value: str | None) -> str:
    if raw_value is not None and _SAFE_ID.fullmatch(raw_value):
        return raw_value
    return str(uuid4())


class CorrelationIdMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = _header_value(scope, _HEADER)
        correlation_id = resolve_correlation_id(incoming)
        state = scope.setdefault("state", {})
        state["correlation_id"] = correlation_id

        async def send_with_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers = [item for item in headers if item[0].lower() != _HEADER]
                headers.append((_HEADER, correlation_id.encode("ascii")))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_id)


def _header_value(scope: Scope, name: bytes) -> str | None:
    for key, value in scope.get("headers", []):
        if key.lower() == name:
            return value.decode("latin-1")
    return None
