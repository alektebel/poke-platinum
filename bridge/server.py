import io
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MAX_BODY = 4096


class BridgeState:
    def __init__(self, app, catalog):
        self.app = app
        self.catalog = catalog


def make_handler(state: BridgeState):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass

        def _json(self, code, obj):
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            app = state.app
            if self.path == "/ping":
                self._json(200, {"ok": True, "frame": app.frame, "fps": round(app.fps(), 1),
                                 "turbo": app.turbo, "controller": app.controller.name if app.controller else None})
            elif self.path == "/state":
                self._json(200, app.sensor.snapshot())
            elif self.path == "/catalog":
                self._json(200, state.catalog)
            elif self.path.startswith("/screen"):
                png, _ = app.last_png()
                if png is None:
                    self._json(503, {"error": "no_frame"})
                    return
                part = "both"
                if "part=bottom" in self.path:
                    part = "bottom"
                elif "part=top" in self.path:
                    part = "top"
                from bridge.screen import crop
                img = crop(png, part)
                buf = io.BytesIO()
                img.save(buf, "PNG")
                data = buf.getvalue()
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            else:
                self._json(404, {"error": "not_found"})

        def do_POST(self):
            if self.path != "/command":
                self._json(404, {"error": "not_found"})
                return
            try:
                length = int(self.headers.get("Content-Length", 0))
                if length > MAX_BODY:
                    self._json(400, {"ok": False, "reason": "too_large"})
                    return
                body = json.loads(self.rfile.read(length) or b"{}")
                if not isinstance(body, dict):
                    raise ValueError
            except Exception:
                self._json(400, {"ok": False, "reason": "bad_json"})
                return
            pending = state.app.submit(body)
            goal = body.get("action") in ("advance_dialog", "walk_to", "menu_navigate", "battle_choice")
            timeout = 180 if goal else 8
            if pending.done.wait(timeout):
                self._json(200, pending.result)
            else:
                self._json(504, {"ok": False, "reason": "timeout"})

    return Handler


def start(state: BridgeState, port):
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(state))
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server
