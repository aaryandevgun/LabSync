"""Local web server: static page + JSON API, standard library only.

    python3 -m labsync_app.web                 # http://127.0.0.1:8000, mock agents, var/labsync_state.json
    python3 -m labsync_app.web --live          # Claude API agents (ANTHROPIC_API_KEY)
    python3 -m labsync_app.web --memory --port 8765

Binds to 127.0.0.1 by default. The demo reset needs LABSYNC_RESET_TOKEN; if it is unset the server
makes a random one for this run and prints it (docs/03: reset is a developer control).
"""
import argparse
import json
import mimetypes
import os
import secrets
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qsl, urlsplit

from labsync_tools.queries import RESET_TOKEN_ENV

STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
MAX_BODY = 64 * 1024
SECURITY_HEADERS = {
    "Content-Security-Policy": "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
}


def make_handler(api):
    class Handler(BaseHTTPRequestHandler):
        server_version = "LabSyncLocal/1"

        def log_message(self, fmt, *args):
            if os.environ.get("LABSYNC_HTTP_LOG"):
                sys.stderr.write("%s %s\n" % (self.address_string(), fmt % args))

        def _send(self, status, body, content_type):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            for k, v in SECURITY_HEADERS.items():
                self.send_header(k, v)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _json(self, status, payload):
            self._send(status, json.dumps(payload, default=str).encode("utf-8"), "application/json; charset=utf-8")

        def _api(self, method):
            url = urlsplit(self.path)
            body = {}
            if method == "POST":
                length = int(self.headers.get("Content-Length") or 0)
                if length > MAX_BODY:
                    return self._json(413, {"status": "error", "code": "TOO_LARGE", "message": "Request too large."})
                raw = self.rfile.read(length) if length else b""
                try:
                    body = json.loads(raw) if raw else {}
                except ValueError:
                    return self._json(400, {"status": "error", "code": "BAD_JSON", "message": "Body must be JSON."})
                if not isinstance(body, dict):
                    return self._json(400, {"status": "error", "code": "BAD_JSON", "message": "Body must be an object."})
            status, payload = api.handle(method, url.path, dict(parse_qsl(url.query)), body,
                                         self.headers.get("X-LabSync-Persona"))
            self._json(status, payload)

        def _static(self):
            path = urlsplit(self.path).path
            rel = "index.html" if path in ("/", "/index.html") else path.lstrip("/")
            if rel.startswith("static/"):
                rel = rel[len("static/"):]
            full = os.path.realpath(os.path.join(STATIC, rel))
            if not full.startswith(os.path.realpath(STATIC) + os.sep) or not os.path.isfile(full):
                return self._send(404, b"Not found", "text/plain; charset=utf-8")
            ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
            if ctype.startswith("text/") or ctype in ("application/javascript",):
                ctype += "; charset=utf-8"
            with open(full, "rb") as fh:
                self._send(200, fh.read(), ctype)

        def do_GET(self):
            if self.path.startswith("/api/"):
                return self._api("GET")
            return self._static()

        do_HEAD = do_GET

        def do_POST(self):
            if not self.path.startswith("/api/"):
                return self._send(405, b"Method not allowed", "text/plain; charset=utf-8")
            return self._api("POST")

    return Handler


def build(live=False, state=None, memory=False):
    from labsync_app.llm import make_client
    from labsync_app.orchestrator import Orchestrator
    from labsync_app.store import DEFAULT_STATE, FileRepository
    from labsync_tools.memory_repo import InMemoryRepository

    from .api import WebAPI
    repo = InMemoryRepository() if memory else FileRepository(state or DEFAULT_STATE)
    client = make_client("live" if live else "mock")
    return WebAPI(Orchestrator(repo, client), mode="live" if live else "mock")


def serve(api, host="127.0.0.1", port=8000):
    httpd = ThreadingHTTPServer((host, port), make_handler(api))
    httpd.daemon_threads = True
    return httpd


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python3 -m labsync_app.web", description="LabSync local web app (no C3)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--live", action="store_true", help="use the Claude API instead of mock agents")
    parser.add_argument("--state", help="state file (default var/labsync_state.json)")
    parser.add_argument("--memory", action="store_true", help="keep state in memory only")
    parser.add_argument("--fresh", action="store_true", help="reset to the seed on start")
    parser.add_argument("--empty-calendar", action="store_true",
                        help="with --fresh: start with no bookings on the calendar (simple booking demo)")
    args = parser.parse_args(argv)
    from labsync_app.llm import LLMUnavailable
    try:
        api = build(args.live, args.state, args.memory)
    except LLMUnavailable as exc:
        print("Live mode unavailable: %s" % exc)
        return 2
    if args.fresh:
        api.repo.reset_to_seed(args.empty_calendar)
    if not os.environ.get(RESET_TOKEN_ENV):
        os.environ[RESET_TOKEN_ENV] = secrets.token_urlsafe(9)
        print("Demo reset token for this run: %s" % os.environ[RESET_TOKEN_ENV], flush=True)
    httpd = serve(api, args.host, args.port)
    print("LabSync local demo · %s agents · http://%s:%d" % (api.mode, args.host, httpd.server_port), flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
