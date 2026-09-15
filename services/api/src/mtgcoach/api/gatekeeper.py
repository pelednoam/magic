"""Turning every request away unless it carries a token, and remembering whose.

ASGI middleware rather than a FastAPI dependency, for two reasons that both
come down to "no route can forget":

- A dependency is attached per route. A route added next month without it is
  open, and nothing says so. This sits in front of all of them.
- ``BaseHTTPMiddleware`` does not see WebSocket connections at all, and the
  socket is the one that streams the whole board. So this is a plain ASGI
  callable, which sees both.

Preflights never reach here. A browser sends ``OPTIONS`` with no
``Authorization`` header -- it is asking whether it *may* send one -- and the
CORS layer sits outside this one and answers it before this is called. That
ordering is load-bearing, and ``guarded`` below is where it is arranged.

**It also decides who is asking.** A token names one seat (see ``seating``), so
this is the only place that knows which, and it writes the answer into the ASGI
scope under ``SEAT``. Everything downstream reads it with ``seat_of`` and never
from the request body: the seat a payload claims is the sender's word for it,
which is precisely what one shared token made unverifiable.
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

from mtgcoach.api.access import presented

if TYPE_CHECKING:
    from starlette.types import ASGIApp, Receive, Scope, Send

    from mtgcoach.api.seating import Seating

#: What a refused request is told. Enough to fix it, and nothing about the
#: token itself -- not its length, not which seat it came closest to, and not
#: how close it was.
REFUSAL = "this server needs a seat's token: send `Authorization: Bearer <token>`"

#: Where the authenticated seat is kept, for the length of one connection.
#:
#: Written into the scope in place, which is what Starlette's own
#: authentication middleware does with ``scope["user"]``: the dict a handler
#: reads is the dict the middleware was given, and a copy would be a second
#: scope for the framework to fill in ``path_params`` on.
#:
#: A dotted key, because the scope is a namespace shared with the server, the
#: framework and any other middleware, and a bare ``"seat"`` is a name somebody
#: else may reasonably want. Nothing but this module writes it, and ``seat_of``
#: is the only thing that reads it.
SEAT = "mtgcoach.seat"


class UnseatedError(RuntimeError):
    """A handler asked which seat it was talking to, outside the gate.

    Not something a client can cause: every route of a ``guarded`` app is
    behind this middleware, so the key is always there by the time a handler
    runs. It is a programming error -- an app assembled without the gate -- and
    it raises rather than defaulting to a seat, because defaulting would hand
    somebody a seat nobody authenticated as.
    """


def seat_of(scope: Scope) -> str:
    """Which seat this connection presented a token for.

    Raises:
        UnseatedError: If this connection never went through the gate.
    """
    found = scope.get(SEAT)
    if not isinstance(found, str):
        msg = f"this connection was not authenticated; {SEAT} is {found!r}"
        raise UnseatedError(msg)
    return found


class Gatekeeper:
    """Refuse anything that does not carry a seat's token."""

    def __init__(self, app: ASGIApp, seating: Seating) -> None:
        """Guard ``app`` with this seating."""
        self._app = app
        self._seating = seating

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

        No exemption for ``OPTIONS`` either. A real preflight never gets this
        far -- CORS sits outside and answers it -- so the only ``OPTIONS`` that
        arrives here is one CORS declined, and letting those through to route
        matching told anybody who could reach the port which paths exist
        (405) and which do not (404).
        """
        seat = self._seat(scope, query=False)
        if seat is not None:
            scope[SEAT] = seat
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
        seat = self._seat(scope, query=True)
        if seat is not None:
            scope[SEAT] = seat
            await self._app(scope, receive, send)
            return
        socket = WebSocket(scope, receive=receive, send=send)
        await socket.close(code=WS_1008_POLICY_VIOLATION, reason=REFUSAL)

    def _seat(self, scope: Scope, *, query: bool) -> str | None:
        """Which seat this connection presented a token for, or None for none."""
        header = Headers(scope=scope).get("authorization")
        found = presented(header, _query_token(scope) if query else None)
        return self._seating.seat(found)


def _query_token(scope: Scope) -> str:
    """The ``token`` query parameter, if there is one."""
    raw = scope.get("query_string", b"")
    found = parse_qs(bytes(raw).decode("latin-1")).get("token", [])
    return found[0] if found else ""


def guarded(seating: Seating) -> FastAPI:
    """A bare app with its two layers of middleware, in the order that matters.

    ``add_middleware`` prepends, so the *last* one added is the outermost. CORS
    has to be outside the gatekeeper: a 401 must come back carrying CORS
    headers or the browser reports an opaque cross-origin error instead of the
    status, and a preflight -- which by definition carries no token -- is
    answered by CORS without reaching the gate at all.

    Open to every origin, and now honestly so. A token is what protects this
    server, and it protects it against all origins equally, so an allowlist
    would be a second thing to keep in step with the app's dev port for no
    gain. The web build is served by Metro on a different port, so every
    request from it is cross-origin.
    """
    app = FastAPI(title="Magic Coach", version="0.1.0")
    # Inside CORS, and outside every route -- including ones added later
    # without anybody remembering. See `gatekeeper` for why it is ASGI
    # middleware rather than a dependency.
    app.add_middleware(Gatekeeper, seating=seating)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    return app
