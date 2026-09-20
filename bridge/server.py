import io
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from bridge.telemetry import Telemetry

MAX_BODY = 4096
WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
MIME = {".html": "text/html", ".js": "text/javascript", ".css": "text/css",
        ".png": "image/png", ".json": "application/json", ".svg": "image/svg+xml"}


class BridgeState:
    def __init__(self, app, catalog):
        self.app = app
        self.catalog = catalog
        self.telemetry = Telemetry()
        self.experiment = None  # set by run_bridge when --record is passed


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

        def _file(self, rel):
            path = os.path.normpath(os.path.join(WEB_DIR, rel))
            if not path.startswith(WEB_DIR) or not os.path.isfile(path):
                self._json(404, {"error": "not_found"})
                return
            ext = os.path.splitext(path)[1]
            data = open(path, "rb").read()
            self.send_response(200)
            self.send_header("Content-Type", MIME.get(ext, "application/octet-stream"))
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            app = state.app
            if self.path in ("/", "/index.html"):
                self._file("index.html")
                return
            if self.path.startswith("/web/"):
                self._file(self.path[len("/web/"):].split("?")[0])
                return
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
            elif self.path == "/telemetry":
                snap = state.telemetry.snapshot(app)
                snap["experiment"] = state.experiment.info() if state.experiment else None
                self._json(200, snap)
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
            # System 2 declares goals either standalone (action=set_goal,
            # level: mission|phase) or attaches a subgoal to a command via "goal".
            if body.get("action") == "set_goal":
                level = body.get("level", "mission")
                state.telemetry.set_goal(body.get("text"), note=body.get("note"),
                                         main=(level != "phase"))
            else:
                goal = body.get("goal")
                if isinstance(goal, str) and goal.strip():
                    state.telemetry.set_goal(goal, note=body.get("goal_note"), main=False)
            t0 = time.time()
            pending = state.app.submit(body)
            timeout = _timeout_for(body)
            if pending.done.wait(timeout):
                pending.result = pending.result or {}
                state.telemetry.record_action(body, pending.result)
                if state.experiment:
                    state.experiment.record_command(body, pending.result, time.time() - t0)
                self._json(200, pending.result)
            else:
                state.telemetry.record_action(body, {"ok": False, "reason": "timeout"})
                if state.experiment:
                    state.experiment.record_command(body, {"ok": False, "reason": "timeout"}, time.time() - t0)
                self._json(504, {"ok": False, "reason": "timeout"})

    return Handler


def _timeout_for(body):
    action = body.get("action", "")
    if action == "set_goal":
        return 10
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
