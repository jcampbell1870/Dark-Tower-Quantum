"""Loopback-only simulation portal with request-size and CSRF protection."""

from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import secrets

from .runtime import MAX_SOURCE_BYTES, TowerError, parse, simulate


ASSETS = Path(__file__).with_name("web")
MAX_REQUEST_BYTES = MAX_SOURCE_BYTES * 6 + 1024


def create_server(port=8765):
    if type(port) is not int or not 0 <= port <= 65535:
        raise TowerError("Port must be between 0 and 65535 (0 chooses a free port).")
    token = secrets.token_hex(32)

    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(10)

        def log_message(self, *_):
            pass

        def reply(self, status, body, content_type="application/json"):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; style-src 'self' 'unsafe-inline'; "
                "frame-ancestors 'none'; base-uri 'none'; object-src 'none'"
            )
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(body)
            self.close_connection = True

        def valid_host(self):
            return self.headers.get("Host") == f"127.0.0.1:{self.server.server_port}"

        def do_GET(self):
            if not self.valid_host():
                self.reply(403, b'{"error":"Invalid host"}')
                return
            files = {"/": ("index.html", "text/html; charset=utf-8"),
                     "/portal.js": ("portal.js", "text/javascript; charset=utf-8")}
            if self.path not in files:
                self.reply(404, b'{"error":"Not found"}')
                return
            filename, content_type = files[self.path]
            body = (ASSETS / filename).read_text(encoding="utf-8")
            if self.path == "/":
                body = body.replace("__TOKEN__", token)
            self.reply(200, body.encode("utf-8"), content_type)

        def do_POST(self):
            origin = f"http://127.0.0.1:{self.server.server_port}"
            supplied_token = self.headers.get("X-Dark-Tower-Token", "")
            if (
                not self.valid_host()
                or self.headers.get("Origin", origin) != origin
                or not secrets.compare_digest(supplied_token.encode(), token.encode())
            ):
                self.reply(403, b'{"error":"Request not authorized"}')
                return
            if self.path != "/api/run":
                self.reply(404, b'{"error":"Not found"}')
                return
            try:
                if self.headers.get("Transfer-Encoding"):
                    raise TowerError("Chunked requests are not supported.")
                if self.headers.get("Content-Type") != "application/json":
                    raise TowerError("Use application/json.")
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= MAX_REQUEST_BYTES:
                    self.reply(413, b'{"error":"Invalid request size"}')
                    return
                request = json.loads(self.rfile.read(length))
                if not isinstance(request, dict) or set(request) - {"source", "shots"}:
                    raise TowerError("Expected source and optional shots only.")
                result = simulate(parse(request.get("source")), request.get("shots", 1024))
                self.reply(200, json.dumps(result).encode())
            except (ValueError, UnicodeError) as exc:
                self.reply(400, json.dumps({"error": str(exc)}).encode())
            except TimeoutError:
                self.reply(408, b'{"error":"Request timed out"}')

    return HTTPServer(("127.0.0.1", port), Handler)


def serve(port=8765):
    with create_server(port) as server:
        print(f"Dark Tower portal: http://127.0.0.1:{server.server_port}", flush=True)
        print("Local simulation only. Press Ctrl+C to stop.", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
