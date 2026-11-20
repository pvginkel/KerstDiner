"""A stand-in for the notification bridge (pvginkel/Notifications), served over HTTP.

The bridge publishes no fake of its own, and the real one sends to Telegram, so
tests of the client and of the report queue talk to this: a WSGI app served on
a free port of 127.0.0.1 by a thread, enforcing the contract of the bridge's
README (a bearer token for ``POST /v1/submit``, a ``400`` for an unknown field
or a blank message, a ``413`` over 4096 characters, a ``404`` or ``405`` for
another path or method, ``GET /healthz`` without a token) and answering the
per-channel result of a registration that has Telegram only.

It records what it accepted, and a test scripts how the next submits fail.
"""

import json
import threading
from dataclasses import dataclass
from types import TracebackType
from typing import Any, Literal
from urllib.parse import urlsplit

from werkzeug.exceptions import MethodNotAllowed, NotFound
from werkzeug.routing import Map, Rule
from werkzeug.serving import make_server
from werkzeug.wrappers import Request, Response

REGISTRATION_NAME = "kerstdiner"
REGISTRATION_TOKEN = "kerstdiner-test-token"

FAILURE_TELEGRAM_ERROR = (
    "error: -100123456789: send: HTTP 403: Forbidden: bot was kicked"
)

Failure = Literal[
    "http_500",  # the bridge answers 500
    "telegram_error",  # 200, with Telegram's error in the result
    "no_telegram",  # 200, with a result that has no Telegram channel
    "not_json",  # 200, with a body that is not JSON
    "not_an_object",  # 200, with a JSON list
    "drop",  # closes the connection without an answer
]

_FIELDS = {"message", "title", "priority", "sequence_id", "url"}
_PRIORITIES = {"min", "low", "default", "high", "max"}
_MAX_MESSAGE = 4096


@dataclass(frozen=True)
class Submit:
    """One accepted submit: its body and the bearer token it came with."""

    body: dict[str, Any]
    bearer: str


class _Refused(Exception):
    def __init__(self, status: int, error: str) -> None:
        self.status = status
        self.error = error


class FakeNotificationBridge:
    """The served stand-in; ``url`` is its base URL.

    ``submits`` holds the submits that were delivered (answered ``{"telegram":
    "ok"}``), in order, and ``attempts`` every valid, authorised submit,
    including the ones a scripted failure answered. Use it as a context
    manager, or call ``close()``.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._failures: list[Failure] = []
        self._healthy = True
        self._submits: list[Submit] = []
        self._attempts: list[Submit] = []
        self._urls = Map(
            [
                Rule("/v1/submit", endpoint="submit", methods=["POST"]),
                Rule("/healthz", endpoint="healthz", methods=["GET"]),
            ]
        )
        self._server = make_server("127.0.0.1", 0, self._wsgi, threaded=True)
        self.url = f"http://127.0.0.1:{self._server.server_port}"
        self.token = REGISTRATION_TOKEN
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="fake-notification-bridge",
            daemon=True,
        )
        self._thread.start()

    # -- What a test reads and scripts ---------------------------------------

    @property
    def submits(self) -> list[Submit]:
        """The delivered submits, oldest first."""
        with self._lock:
            return list(self._submits)

    @property
    def attempts(self) -> list[Submit]:
        """Every valid, authorised submit, failed ones included, oldest first."""
        with self._lock:
            return list(self._attempts)

    def fail_next(self, count: int, how: Failure = "http_500") -> None:
        """Fail the next ``count`` valid submits the way ``how`` says."""
        with self._lock:
            self._failures.extend([how] * count)

    def set_healthy(self, healthy: bool) -> None:
        """Have ``/healthz`` answer 200 (healthy) or 503."""
        with self._lock:
            self._healthy = healthy

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join()

    def __enter__(self) -> "FakeNotificationBridge":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    # -- The bridge ------------------------------------------------------------

    def _wsgi(self, environ: Any, start_response: Any) -> Any:
        request = Request(environ)
        response = self._respond(request)
        if response is None:
            # Close the connection without an answer.
            environ["werkzeug.socket"].shutdown(2)
            environ["werkzeug.socket"].close()
            response = Response("", status=500)
        return response(environ, start_response)

    def _respond(self, request: Request) -> Response | None:
        try:
            endpoint, _ = self._urls.bind_to_environ(request.environ).match()
        except NotFound:
            return Response("404 page not found", status=404, mimetype="text/plain")
        except MethodNotAllowed:
            return Response("405 method not allowed", status=405, mimetype="text/plain")

        if endpoint == "healthz":
            with self._lock:
                healthy = self._healthy
            if healthy:
                return Response("ok", mimetype="text/plain")
            return Response("unhealthy", status=503, mimetype="text/plain")
        return self._submit(request)

    def _submit(self, request: Request) -> Response | None:
        try:
            bearer = self._bearer_of(request)
            body = self._validated(request)
        except _Refused as refused:
            response = _json({"error": refused.error}, refused.status)
            if refused.status == 401:
                response.headers["WWW-Authenticate"] = "Bearer"
            return response

        accepted = Submit(body, bearer)
        with self._lock:
            self._attempts.append(accepted)
            failure = self._failures.pop(0) if self._failures else None
            if failure is None:
                self._submits.append(accepted)

        if failure is None:
            return _json({"telegram": "ok"})
        if failure == "http_500":
            return _json({"error": "the bridge broke"}, 500)
        if failure == "telegram_error":
            return _json({"telegram": FAILURE_TELEGRAM_ERROR})
        if failure == "no_telegram":
            return _json({})
        if failure == "not_json":
            return Response("<html>not the bridge</html>", mimetype="text/html")
        if failure == "not_an_object":
            return _json(["ok"])
        return None

    def _bearer_of(self, request: Request) -> str:
        scheme, _, token = request.headers.get("Authorization", "").partition(" ")
        if scheme.lower() != "bearer" or token != self.token:
            raise _Refused(401, "unknown bearer token")
        return token

    def _validated(self, request: Request) -> dict[str, Any]:
        try:
            body = json.loads(request.get_data())
        except ValueError:
            raise _Refused(400, "the body is not JSON") from None
        if not isinstance(body, dict):
            raise _Refused(400, "the body is not a JSON object")
        body = {key: value for key, value in body.items() if value is not None}

        unknown = sorted(set(body) - _FIELDS)
        if unknown:
            raise _Refused(400, f"unknown field {unknown[0]!r}")
        for key, value in body.items():
            if not isinstance(value, str):
                raise _Refused(400, f"{key} is not a string")

        message = body.get("message")
        if message is None or not message.strip():
            raise _Refused(400, "message is required and not blank")
        if len(body.get("title", "")) > 250:
            raise _Refused(400, "title is over 250 characters")
        if "priority" in body and body["priority"] not in _PRIORITIES:
            raise _Refused(400, "unknown priority")
        if "sequence_id" in body and not 1 <= len(body["sequence_id"]) <= 256:
            raise _Refused(400, "sequence_id is not 1 to 256 characters")
        if "url" in body:
            parts = urlsplit(body["url"])
            if (
                len(body["url"]) > 2048
                or parts.scheme not in ("http", "https")
                or not parts.netloc
            ):
                raise _Refused(400, "url is not an http(s) URL")
        if len(message) > _MAX_MESSAGE:
            raise _Refused(413, f"message is over {_MAX_MESSAGE} characters")
        return body


def _json(body: Any, status: int = 200) -> Response:
    return Response(json.dumps(body), status=status, mimetype="application/json")
