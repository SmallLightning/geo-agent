"""Zero-dependency web UI for the geo agent.

    python3 src/web.py            # http://127.0.0.1:8000
    python3 src/web.py --port 8080

Uses only the standard library (http.server + ThreadingHTTPServer), so it also works
on an offline judge machine: without an AMAP_KEY the API falls back to fixtures.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from src.agent import run  # noqa: E402

INDEX_HTML = os.path.join(ROOT, "web", "index.html")


class Handler(BaseHTTPRequestHandler):
    server_version = "geo-agent/1.0"

    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, payload: dict) -> None:
        self._send(code, json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def do_GET(self) -> None:  # noqa: N802
        if self.path in ("/", "/index.html"):
            try:
                with open(INDEX_HTML, "rb") as fh:
                    self._send(200, fh.read(), "text/html; charset=utf-8")
            except OSError:
                self._send(500, b"index.html missing", "text/plain; charset=utf-8")
        elif self.path == "/api/health":
            self._json(200, {"ok": True})
        else:
            self._send(404, b"not found", "text/plain; charset=utf-8")

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/api/ask":
            self._send(404, b"not found", "text/plain; charset=utf-8")
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
            text = (payload.get("text") or "").strip()
            if not text:
                self._json(400, {"ok": False, "error": "请输入一句话需求"})
                return
            out = run(text, use_llm=True, offline=bool(payload.get("offline")))
            self._json(200, out)
        except Exception as exc:  # noqa: BLE001 - never crash the server
            self._json(500, {"ok": False, "error": f"{type(exc).__name__}: {exc}"})

    def log_message(self, fmt, *args):  # quieter console
        sys.stderr.write("[web] " + (fmt % args) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description="geo-agent web UI")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()

    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"geo-agent UI -> http://{args.host}:{args.port}")
    print("Ctrl+C 停止")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
