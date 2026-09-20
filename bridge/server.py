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
            elif self.path.startswith("/events"):
                since = int(self.path.split("since=")[1].split("&")[0]) if "since=" in self.path else 0
                mem = getattr(app, "memory", None)
                self._json(200, {"events": mem.events_since(since) if mem else []})
            elif self.path == "/memory":
                mem = getattr(app, "memory", None)
                self._json(200, mem.snapshot() if mem else {"error": "no_memory"})
            elif self.path.startswith("/mem"):
                try:
                    qs = self.path.split("?", 1)[1] if "?" in self.path else ""
                    params = dict(p.split("=", 1) for p in qs.split("&") if "=" in p)
                    addr = int(params.get("addr", "0"), 0)
                    length = min(int(params.get("len", "256"), 0), 1 << 20)
                    data = bytes(app.emu.memory.read(addr, addr + length, 1, False))
                    self._json(200, {"addr": hex(addr), "len": length, "hex": data.hex()})
                except Exception as e:
                    self._json(400, {"error": f"bad_mem:{e}"})
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
            timeout = _timeout_for(body)
            if pending.done.wait(timeout):
                self._json(200, pending.result)
            else:
                self._json(504, {"ok": False, "reason": "timeout"})

    return Handler


def _timeout_for(body):
    action = body.get("action", "")
    if action in ("advance_dialog", "walk_to", "menu_navigate", "battle_fight"):
        return 600
    if action in ("debug_scan", "debug_mark", "debug_diff"):
        return 300
    if action == "wait":
        try:
            return min(int(body.get("frames", 1)) / 30.0 + 10, 180)
        except (TypeError, ValueError):
            return 20
    return 60


def start(state: BridgeState, port):
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(state))
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server
