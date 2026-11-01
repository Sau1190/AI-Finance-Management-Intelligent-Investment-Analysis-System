"""Request-size limit and response hardening headers (Phase 14).

Beginner view:
  Two small guards in front of every request. One refuses a body that is
  bigger than allowed *before* the app reads it all into memory; the other
  adds standard browser-safety headers to every answer.

Technical view:
  Pure ASGI middleware (no FastAPI/SQLAlchemy import, so it is unit-tested
  against a plain ASGI app). A declared Content-Length over the limit is
  refused without calling the app. A body that lies about (or omits) its
  length is counted while streaming; once the limit is passed the app is cut
  off with a disconnect and the client always receives our 413 envelope,
  whatever the app tried to answer.
"""

import json
from collections.abc import Callable

# rule(scope) -> (limit_bytes, error_code, message) or None for "no limit".
SizeRule = Callable[[dict], "tuple[int, str, str] | None"]

DEFAULT_SECURITY_HEADERS: tuple[tuple[bytes, bytes], ...] = (
    (b"x-content-type-options", b"nosniff"),
    (b"cache-control", b"no-store"),
    (b"referrer-policy", b"no-referrer"),
    (b"x-frame-options", b"DENY"),
)
# Interactive API docs load their own assets; leave them untouched.
DEFAULT_SKIP_PREFIXES: tuple[str, ...] = ("/docs", "/redoc", "/openapi.json")


def _envelope(code: str, message: str) -> bytes:
    return json.dumps({"detail": {"code": code, "message": message}}).encode("utf-8")


class RequestSizeLimitMiddleware:
    def __init__(self, app, limit_for: SizeRule) -> None:
        self.app = app
        self.limit_for = limit_for

    async def __call__(self, scope, receive, send) -> None:
        rule = self.limit_for(scope) if scope["type"] == "http" else None
        if rule is None:
            await self.app(scope, receive, send)
            return
        limit, code, message = rule

        declared = None
        for name, value in scope.get("headers", []):
            if name == b"content-length":
                try:
                    declared = int(value)
                except ValueError:
                    declared = None
                break
        if declared is not None and declared > limit:
            await self._refuse(send, code, message)
            return

        state = {"received": 0, "exceeded": False, "started": False, "refused": False}

        async def limited_receive():
            if state["exceeded"]:
                return {"type": "http.disconnect"}
            message_in = await receive()
            if message_in["type"] == "http.request":
                state["received"] += len(message_in.get("body", b""))
                if state["received"] > limit:
                    state["exceeded"] = True
                    return {"type": "http.disconnect"}
            return message_in

        async def guarded_send(message_out) -> None:
            if state["exceeded"] and not state["started"]:
                # Whatever the app tried to say after being cut off, the answer is our 413.
                if not state["refused"]:
                    state["refused"] = True
                    await self._refuse(send, code, message)
                return
            if message_out["type"] == "http.response.start":
                state["started"] = True
            await send(message_out)

        try:
            await self.app(scope, limited_receive, guarded_send)
        except Exception:
            if not (state["exceeded"] and not state["started"]):
                raise
        if state["exceeded"] and not state["started"] and not state["refused"]:
            state["refused"] = True
            await self._refuse(send, code, message)

    @staticmethod
    async def _refuse(send, code: str, message: str) -> None:
        body = _envelope(code, message)
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                    (b"connection", b"close"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})


class SecurityHeadersMiddleware:
    def __init__(
        self,
        app,
        headers: tuple[tuple[bytes, bytes], ...] = DEFAULT_SECURITY_HEADERS,
        skip_prefixes: tuple[str, ...] = DEFAULT_SKIP_PREFIXES,
    ) -> None:
        self.app = app
        self.headers = headers
        self.skip_prefixes = skip_prefixes

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http" or scope.get("path", "").startswith(self.skip_prefixes):
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message) -> None:
            if message["type"] == "http.response.start":
                merged = list(message.get("headers", []))
                existing = {name.lower() for name, _ in merged}
                # The app's own header always wins; ours only fill gaps.
                merged.extend((n, v) for n, v in self.headers if n not in existing)
                message = {**message, "headers": merged}
            await send(message)

        await self.app(scope, receive, send_with_headers)
