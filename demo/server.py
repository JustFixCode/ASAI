"""Loopback-only HTTP UI for the ASAI simulator (not a broker service)."""
from __future__ import annotations

import argparse
import hmac
import json
import os
import secrets
import sys
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

MAX_BODY_BYTES = 16 * 1024
SOCKET_TIMEOUT_SECONDS = 5
INDEX_PATH = Path(__file__).with_name("index.html")


class BadRequest(ValueError):
    """An input error whose message is safe to return to a local UI."""

    def __init__(self, message: str, code: str = "invalid_request") -> None:
        super().__init__(message)
        self.code = code


def _no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise BadRequest("JSON object contains a duplicate key")
        result[key] = value
    return result


def _json_loads(raw: bytes) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_no_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError, BadRequest) as exc:
        raise BadRequest("body must be a valid JSON object") from exc
    if not isinstance(value, dict):
        raise BadRequest("body must be a JSON object")
    return value


class DemoHTTPServer(ThreadingHTTPServer):
    """In-memory simulator server deliberately restricted to local loopback."""

    allow_reuse_address = False
    daemon_threads = True

    def __init__(self, server_address: tuple[str, int], simulator: Any, quote_provider: Any):
        host, _port = server_address
        if host != "127.0.0.1":
            raise ValueError("demo server must bind exactly to 127.0.0.1")
        super().__init__(server_address, DemoRequestHandler)
        self.simulator = simulator
        self.quote_provider = quote_provider
        self.session_token = secrets.token_urlsafe(32)
        self.csrf_token = secrets.token_urlsafe(32)

    def get_request(self) -> tuple[Any, tuple[str, int]]:
        """Bound incomplete requests so one local client cannot stall the UI."""
        request, client_address = super().get_request()
        request.settimeout(SOCKET_TIMEOUT_SECONDS)
        return request, client_address


class DemoRequestHandler(BaseHTTPRequestHandler):
    server: DemoHTTPServer
    protocol_version = "HTTP/1.1"
    server_version = "ASAI-Local-Simulator"
    sys_version = ""

    def log_message(self, _format: str, *_args: Any) -> None:
        # Never log request paths, headers, bodies, or exception details: these can hold tokens.
        return

    def _valid_host(self) -> bool:
        expected = f"127.0.0.1:{self.server.server_port}"
        values = self.headers.get_all("Host") or []
        return len(values) == 1 and hmac.compare_digest(values[0], expected)

    def _send_json(self, status: int, value: dict[str, Any]) -> None:
        data = json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            self.wfile.write(data)
        except OSError:
            # A disconnected client is not an application error and must not
            # create a traceback that could include request details.
            self.close_connection = True

    def _error(self, status: int, code: str) -> None:
        self._send_json(status, {"error": code})

    def _check_host(self) -> bool:
        if self._valid_host():
            return True
        self._error(HTTPStatus.BAD_REQUEST, "invalid_host")
        return False

    def _authenticated(self) -> bool:
        values = self.headers.get_all("X-Session-Token") or []
        supplied = values[0] if len(values) == 1 else ""
        if not supplied or not hmac.compare_digest(supplied, self.server.session_token):
            self._error(HTTPStatus.UNAUTHORIZED, "authentication_required")
            return False
        return True

    def _post_allowed(self) -> bool:
        expected_origin = f"http://127.0.0.1:{self.server.server_port}"
        origins = self.headers.get_all("Origin") or []
        csrf_values = self.headers.get_all("X-CSRF-Token") or []
        origin = origins[0] if len(origins) == 1 else ""
        csrf = csrf_values[0] if len(csrf_values) == 1 else ""
        if not hmac.compare_digest(origin, expected_origin):
            self._error(HTTPStatus.FORBIDDEN, "invalid_origin")
            return False
        if not csrf or not hmac.compare_digest(csrf, self.server.csrf_token):
            self._error(HTTPStatus.FORBIDDEN, "csrf_required")
            return False
        return True

    def _read_json(self) -> dict[str, Any]:
        content_types = self.headers.get_all("Content-Type") or []
        content_type = content_types[0] if len(content_types) == 1 else ""
        media_type = content_type.split(";", 1)[0].strip().lower()
        if media_type != "application/json":
            # The declared body has not been consumed, so close rather than
            # interpreting it as a subsequent request on a keep-alive socket.
            self.close_connection = True
            raise BadRequest("content type must be application/json")
        lengths = self.headers.get_all("Content-Length") or []
        raw_length = lengths[0] if len(lengths) == 1 else None
        if raw_length is None or not raw_length.isdecimal():
            self.close_connection = True
            raise BadRequest("content length is required")
        length = int(raw_length)
        if length > MAX_BODY_BYTES:
            # Do not parse rejected request bytes as another HTTP/1.1 request.
            self.close_connection = True
            raise BadRequest("request body is too large")
        raw = self.rfile.read(length)
        if len(raw) != length:
            self.close_connection = True
            raise BadRequest("incomplete request body")
        return _json_loads(raw)

    def _api_get(self, path: str, query: dict[str, list[str]]) -> None:
        if path == "/api/bootstrap" and not query:
            self._send_json(HTTPStatus.OK, {"csrf_token": self.server.csrf_token})
            return
        if path == "/api/snapshot" and not query:
            self._send_json(HTTPStatus.OK, {"snapshot": self.server.simulator.snapshot()})
            return
        if path == "/api/quote" and set(query) <= {"symbol"} and len(query.get("symbol", [])) <= 1:
            symbol = query.get("symbol", [""])[0]
            if symbol and (not symbol.isascii() or not symbol.isalnum() or len(symbol) > 12):
                raise BadRequest("symbol must be 1-12 alphanumeric characters")
            quote = _get_quote(self.server.quote_provider, symbol or "AAPL")
            self._send_json(HTTPStatus.OK, {"quote": _public_value(quote)})
            return
        self._error(HTTPStatus.NOT_FOUND, "not_found")

    def do_GET(self) -> None:  # noqa: N802
        if not self._check_host():
            return
        parsed = urlsplit(self.path)
        if parsed.path == "/health" and not parsed.query:
            self._send_json(HTTPStatus.OK, {"status": "ok", "service": "local_simulator"})
            return
        if parsed.path == "/" and not parsed.query:
            try:
                data = INDEX_PATH.read_bytes()
            except OSError:
                self._error(HTTPStatus.INTERNAL_SERVER_ERROR, "ui_unavailable")
                return
            try:
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Referrer-Policy", "no-referrer")
                self.end_headers()
                self.wfile.write(data)
            except OSError:
                self.close_connection = True
            return
        if not parsed.path.startswith("/api/"):
            self._error(HTTPStatus.NOT_FOUND, "not_found")
            return
        if not self._authenticated():
            return
        try:
            self._api_get(parsed.path, parse_qs(parsed.query, keep_blank_values=True, strict_parsing=True))
        except (BadRequest, ValueError):
            self._error(HTTPStatus.BAD_REQUEST, "invalid_request")

    def do_POST(self) -> None:  # noqa: N802
        if not self._check_host() or not self._authenticated() or not self._post_allowed():
            return
        parsed = urlsplit(self.path)
        if parsed.query:
            self._error(HTTPStatus.BAD_REQUEST, "invalid_request")
            return
        try:
            payload = self._read_json()
            if parsed.path == "/api/orders":
                if set(payload) - {"order", "idempotency_key", "quote_symbol"}:
                    raise BadRequest("unknown field")
                order = payload.get("order")
                key = payload.get("idempotency_key")
                quote_symbol = payload.get("quote_symbol", "AAPL")
                if not isinstance(order, dict) or not isinstance(key, str) or not key or len(key) > 128:
                    raise BadRequest("invalid order request")
                if not isinstance(quote_symbol, str) or not quote_symbol.isalnum() or len(quote_symbol) > 12:
                    raise BadRequest("invalid quote symbol")
                if order.get("symbol") != "AAPL":
                    raise BadRequest("unsupported order symbol", "unsupported_symbol")
                if quote_symbol != order["symbol"]:
                    raise BadRequest("quote symbol does not match order symbol", "quote_symbol_mismatch")
                quote = _get_quote(self.server.quote_provider, quote_symbol)
                result = self.server.simulator.place_order(order, key, quote, datetime.now(timezone.utc))
                self._send_json(HTTPStatus.OK, {"order": _public_value(result)})
                return
            prefix = "/api/orders/"
            suffix = "/cancel"
            if parsed.path.startswith(prefix) and parsed.path.endswith(suffix):
                order_id = parsed.path[len(prefix):-len(suffix)]
                if not order_id or "/" in order_id or len(order_id) > 128 or payload:
                    raise BadRequest("invalid cancel request")
                result = self.server.simulator.cancel_order(order_id)
                self._send_json(HTTPStatus.OK, {"order": _public_value(result)})
                return
            self._error(HTTPStatus.NOT_FOUND, "not_found")
        except BadRequest as exc:
            safe_code = getattr(exc, "code", None)
            self._error(HTTPStatus.BAD_REQUEST, safe_code if isinstance(safe_code, str) and safe_code.isidentifier() else "invalid_request")
        except Exception as exc:  # Simulator errors must not turn into server tracebacks.
            safe_code = getattr(exc, "code", None)
            self._error(HTTPStatus.BAD_REQUEST, safe_code if isinstance(safe_code, str) and safe_code.isidentifier() else "order_rejected")


def _get_quote(provider: Any, symbol: str) -> Any:
    """Use the quote-provider protocol without granting it any other capability."""
    getter = getattr(provider, "get_quote", None)
    if callable(getter):
        return getter(symbol)
    # Kept for small local test doubles; production make_quote_provider returns
    # the protocol object above.
    if callable(provider):
        return provider(symbol)
    raise BadRequest("quote provider is unavailable")


def _public_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _public_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_public_value(item) for item in value]
    if hasattr(value, "__dict__"):
        return {key: _public_value(item) for key, item in vars(value).items() if not key.startswith("_")}
    return str(value)


def make_server(port: int = 0, quote_mode: str = "fixture") -> DemoHTTPServer:
    """Construct, but do not start, the local server (convenient for tests)."""
    from demo.quotes import make_quote_provider
    from demo.simulator import DemoSimulator

    if port < 0 or port > 65535:
        raise ValueError("port must be between 0 and 65535")
    return DemoHTTPServer(("127.0.0.1", port), DemoSimulator(), make_quote_provider(quote_mode))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ASAI local simulator UI; not real-money trading or a broker.")
    parser.add_argument("--port", type=int, default=0, help="loopback port (default: random available port)")
    parser.add_argument("--quote-mode", choices=("unavailable", "fixture", "alpaca_iex"), default="fixture")
    args = parser.parse_args(argv)
    server = make_server(args.port, args.quote_mode)
    url = f"http://127.0.0.1:{server.server_port}/"
    print(f"ASAI local simulator (not a broker or real-money service): {url}", flush=True)
    print("Enter this local session token in the page (it is never placed in the URL):", flush=True)
    print(server.session_token, flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
