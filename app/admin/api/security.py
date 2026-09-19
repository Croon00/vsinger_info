"""Loopback-only, same-origin cookie + CSRF guard."""

import secrets
import time
from http.cookies import SimpleCookie
from starlette.responses import JSONResponse

COOKIE = "catalog_admin_session"


class LocalGuard:
    def __init__(self, app, origins, sessions):
        self.app = app
        self.origins = set(origins)
        self.hosts = {o.split("://", 1)[1] for o in origins}
        self.sessions = sessions

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = {k.decode().lower(): v.decode() for k, v in scope["headers"]}

        async def reject(message, status=403):
            await JSONResponse({"detail": message}, status_code=status)(
                scope, receive, send
            )

        if (
            scope.get("client", ("unknown",))[0] not in {"127.0.0.1", "::1"}
            or headers.get("host", "") not in self.hosts
        ):
            return await reject("이 관리 도구는 로컬 PC에서만 사용할 수 있습니다.")
        origin = headers.get("origin")
        if origin and origin not in self.origins:
            return await reject("허용되지 않은 요청 출처입니다.")
        if headers.get("sec-fetch-site") == "cross-site":
            return await reject("외부 사이트의 요청은 허용하지 않습니다.")
        if scope["path"].startswith("/api/admin"):
            cookie = SimpleCookie()
            try:
                cookie.load(headers.get("cookie", ""))
            except Exception:
                return await reject("세션을 다시 열어 주세요.", 401)
            item = cookie.get(COOKIE)
            key = item.value if item else ""
            session = self.sessions.get(key)
            if scope["path"] != "/api/admin/session":
                if not session or session["expires"] < time.time():
                    return await reject(
                        "관리 세션이 만료되었습니다. 화면을 새로고침하세요.", 401
                    )
                session["expires"] = time.time() + 8 * 3600
                if scope["method"] not in {"GET", "HEAD"}:
                    if origin not in self.origins or not secrets.compare_digest(
                        headers.get("x-csrf-token", ""), session["csrf"]
                    ):
                        return await reject(
                            "요청을 확인할 수 없습니다. 화면을 새로고침하세요."
                        )
            if scope["method"] not in {"GET", "HEAD"}:
                chunks = []
                size = 0
                original_receive = receive
                while True:
                    event = await original_receive()
                    if event["type"] == "http.disconnect":
                        return
                    size += len(event.get("body", b""))
                    if size > 12 * 1024 * 1024:
                        return await reject("요청은 최대 12MiB입니다.", 413)
                    chunks.append(event.get("body", b""))
                    if not event.get("more_body"):
                        break
                sent = False

                async def body_receive():
                    nonlocal sent
                    if not sent:
                        sent = True
                        return {
                            "type": "http.request",
                            "body": b"".join(chunks),
                            "more_body": False,
                        }
                    return await original_receive()

                receive = body_receive

        async def safe_send(event):
            if event["type"] == "http.response.start":
                event["headers"] = list(event["headers"]) + [
                    (b"x-content-type-options", b"nosniff"),
                    (b"x-frame-options", b"DENY"),
                    (b"referrer-policy", b"no-referrer"),
                    (b"cache-control", b"no-store"),
                    (
                        b"content-security-policy",
                        b"frame-ancestors 'none'; object-src 'none'; base-uri 'self'",
                    ),
                ]
            await send(event)

        await self.app(scope, receive, safe_send)
