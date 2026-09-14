"""Turning every request away unless it carries the token.

ASGI middleware rather than a FastAPI dependency, for two reasons that both
come down to "no route can forget":

- A dependency is attached per route. A route added next month without it is
  open, and nothing says so. This sits in front of all of them.
- ``BaseHTTPMiddleware`` does not see WebSocket connections at all, and the
  socket is the one that streams the whole board. So this is a plain ASGI
  callable, which sees both.

Preflights go through unanswered by design. A browser sends ``OPTIONS`` with no
``Authorization`` header -- it is asking whether it *may* send one -- so
refusing it would refuse the request that follows, and the preflight reveals
nothing but the CORS policy.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import parse_qs

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.status import HTTP_401_UNAUTHORIZED, WS_1008_POLICY_VIOLATION
from starlette.websockets import WebSocket

from mtgcoach.api.access import allowed, presented

if TYPE_CHECKING:
    from starlette.types import ASGIApp, Receive, Scope, Send

#: What a refused request is told. Enough to fix it, and nothing about the
#: token itself -- not its length, and not how close the attempt was.
REFUSAL = "this server needs its token: send `Authorization: Bearer <token>`"

#: The method a browser uses to ask whether it may send a real request.
PREFLIGHT = "OPTIONS"


class Gatekeeper:
    """Refuse anything that does not carry the token."""

    def __init__(self, app: ASGIApp, token: str) -> None:
        """Guard ``app`` with this token."""
        self._app = app
        self._token = token

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Let it through, or turn it away in the way its protocol expects."""
        if scope["type"] == "http":
            await self._http(scope, receive, send)
        elif scope["type"] == "websocket":
            await self._socket(scope, receive, send)
        else:
            # Lifespan. There is no request to authorise and nothing to refuse.
            await self._app(scope, receive, send)

    async def _http(self, scope: Scope, receive: Receive, send: Send) -> None:
        """One HTTP request.

        The header only. The query string is the socket's escape hatch and
        nothing else's: accepting it here would invite a token into URLs that
        reach access logs, proxies and browser history, for no gain -- an HTTP
        client can always set a header.
        """
        if scope.get("method") == PREFLIGHT or self._carries(scope, query=False):
            await self._app(scope, receive, send)
            return
        refused = JSONResponse({"detail": REFUSAL}, status_code=HTTP_401_UNAUTHORIZED)
        await refused(scope, receive, send)

    async def _socket(self, scope: Scope, receive: Receive, send: Send) -> None:
        """One WebSocket connection.

        Closed *without* being accepted first, which is the point: never open a
        connection you are about to refuse. What the client sees then depends
        on the transport -- uvicorn turns it into a 403 on the handshake, while
        Starlette's test client reports the close code -- and neither carries
        the reason very far. That is fine here: the app makes an HTTP request
        before it ever opens a socket, so a missing token has already produced
        a 401 with a sentence on it.
        """
        if self._carries(scope, query=True):
            await self._app(scope, receive, send)
            return
        socket = WebSocket(scope, receive=receive, send=send)
        await socket.close(code=WS_1008_POLICY_VIOLATION, reason=REFUSAL)

    def _carries(self, scope: Scope, *, query: bool) -> bool:
        """Whether this connection presented the token."""
        header = Headers(scope=scope).get("authorization")
        found = presented(header, _query_token(scope) if query else None)
        return allowed(found, self._token)


def _query_token(scope: Scope) -> str:
    """The ``token`` query parameter, if there is one."""
    raw = scope.get("query_string", b"")
    found = parse_qs(bytes(raw).decode("latin-1")).get("token", [])
    return found[0] if found else ""


def guarded(token: str) -> FastAPI:
    """A bare app with its two layers of middleware, in the order that matters.

    ``add_middleware`` prepends, so the *last* one added is the outermost. CORS
    has to be outside the gatekeeper: a 401 must come back carrying CORS
    headers or the browser reports an opaque cross-origin error instead of the
    status, and a preflight -- which by definition carries no token -- is
    answered by CORS without reaching the gate at all.

    Open to every origin, and now honestly so. The token is what protects this
    server, and it protects it against all origins equally, so an allowlist
    would be a second thing to keep in step with the app's dev port for no
    gain. The web build is served by Metro on a different port, so every
    request from it is cross-origin.
    """
    app = FastAPI(title="Magic Coach", version="0.1.0")
    # Inside CORS, and outside every route -- including ones added later
    # without anybody remembering. See `gatekeeper` for why it is ASGI
    # middleware rather than a dependency.
    app.add_middleware(Gatekeeper, token=token)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    return app
