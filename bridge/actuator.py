from bridge.keys import KEY_NAMES

MAX_FRAMES = 3600
GOAL_TIMEOUT_HINT = 120


def execute(app, body):
    action = body.get("action")
    if not isinstance(action, str):
        return {"ok": False, "reason": "missing_action"}

    try:
        if action == "tap":
            key = _key(body)
            if key is None:
                return {"ok": False, "reason": "bad_key"}
            frames = _int(body, "frames", 2)
            app.press([key], frames=frames)
            return {"ok": True, "frame": app.frame}

        if action == "press":
            keys = body.get("keys")
            if not isinstance(keys, list) or not keys or not all(isinstance(k, str) and k.upper() in KEY_NAMES for k in keys):
                return {"ok": False, "reason": "bad_keys"}
            frames = _int(body, "frames", 2)
            app.press([k.upper() for k in keys], frames=frames)
            return {"ok": True, "frame": app.frame}

        if action == "hold":
            key = _key(body)
            if key is None:
                return {"ok": False, "reason": "bad_key"}
            app.hold([key])
            return {"ok": True, "frame": app.frame}

        if action == "release":
            key = _key(body)
            if key is None:
                return {"ok": False, "reason": "bad_key"}
            app.release([key])
            return {"ok": True, "frame": app.frame}

        if action == "release_all":
            app.release_all()
            return {"ok": True, "frame": app.frame}

        if action == "touch":
            x, y = body.get("x"), body.get("y")
            if not _coord(x) or not _coord(y):
                return {"ok": False, "reason": "bad_coords"}
            app.touch(int(x), int(y))
            return {"ok": True, "frame": app.frame}

        if action == "touch_release":
            app.touch_release()
            return {"ok": True, "frame": app.frame}

        if action == "wait":
            n = _int(body, "frames", 1)
            app.run_frames(max(1, min(n, MAX_FRAMES)))
            return {"ok": True, "frame": app.frame}

        if action == "reset":
            app.release_all()
            app.controller = None
            app.emu.reset()
            return {"ok": True, "frame": app.frame}

        if action == "savestate":
            path = body.get("file")
            if not isinstance(path, str) or not path:
                return {"ok": False, "reason": "bad_file"}
            app.savestate(path)
            return {"ok": True, "file": path, "frame": app.frame}

        if action == "loadstate":
            path = body.get("file")
            if not isinstance(path, str) or not path:
                return {"ok": False, "reason": "bad_file"}
            app.loadstate(path)
            return {"ok": True, "file": path, "frame": app.frame}

        if action == "turbo":
            app.turbo = bool(body.get("on", True))
            return {"ok": True, "turbo": app.turbo}

        if action == "stop_goal":
            app.controller = None
            app.release_all()
            return {"ok": True, "frame": app.frame}

        if action == "advance_dialog":
            from bridge.controllers import DialogController
            return _start_controller(app, DialogController(body))

        if action == "walk_to":
            from bridge.controllers import WalkController
            x, y = body.get("x"), body.get("y")
            if not isinstance(x, int) or not isinstance(y, int):
                return {"ok": False, "reason": "bad_coords"}
            return _start_controller(app, WalkController(x, y, body))

        if action == "menu_navigate":
            from bridge.controllers import MenuController
            return _start_controller(app, MenuController(body))

        if action == "battle_choice":
            from bridge.controllers import BattleController
            return _start_controller(app, BattleController(body))

        if action == "debug_read":
            addr = _parse_int(body.get("addr", 0))
            n = min(_parse_int(body.get("len", 16)), 4096)
            data = app.emu.memory.read(addr, addr + n, 1, False)
            return {"ok": True, "addr": hex(addr), "hex": bytes(data).hex()}

        if action == "debug_scan":
            start = _parse_int(body.get("start", 0x02000000))
            end = min(_parse_int(body.get("end", 0x02400000)), 0x02400000)
            value = _parse_int(body["value"])
            size = _parse_int(body.get("size", 4))
            mask = _parse_int(body.get("mask", 0xFFFFFFFF))
            data = bytes(app.emu.memory.read(start, end, 1, False))
            hits = []
            for off in range(0, len(data) - size + 1, 4):
                v = int.from_bytes(data[off:off + size], "little")
                if (v & mask) == (value & mask):
                    hits.append(hex(start + off))
                    if len(hits) >= 200:
                        break
            return {"ok": True, "hits": hits, "count": len(hits)}

        if action == "debug_mark":
            data = bytes(app.emu.memory.read(0x02000000, 0x023FFFFF, 1, False))
            app._mem_mark = data
            return {"ok": True, "note": "snapshot stored"}

        if action == "debug_diff":
            old = getattr(app, "_mem_mark", None)
            if old is None:
                return {"ok": False, "reason": "no_mark"}
            new = bytes(app.emu.memory.read(0x02000000, 0x023FFFFF, 1, False))
            out = []
            for off in range(0, len(new) - 4, 4):
                if new[off:off + 4] != old[off:off + 4]:
                    ov = int.from_bytes(old[off:off + 4], "little")
                    nv = int.from_bytes(new[off:off + 4], "little")
                    out.append((hex(0x02000000 + off), hex(ov), hex(nv)))
                    if len(out) >= 400:
                        break
            return {"ok": True, "changes": out, "count": len(out)}

        return {"ok": False, "reason": f"unknown_action:{action}"}
    except Exception as e:
        return {"ok": False, "reason": f"exception:{type(e).__name__}:{e}"}


def _start_controller(app, controller):
    app.controller = controller
    return {"ok": True, "goal_started": controller.name, "frame": app.frame,
            "note": f"poll /state; goal runs up to {GOAL_TIMEOUT_HINT}s on the emu thread"}


def _key(body):
    k = body.get("key", "")
    return k.upper() if isinstance(k, str) and k.upper() in KEY_NAMES else None


def _int(body, field, default):
    v = body.get(field, default)
    try:
        return max(1, min(int(v), MAX_FRAMES))
    except (TypeError, ValueError):
        return default


def _coord(v):
    return isinstance(v, (int, float)) and 0 <= v < 256


def _parse_int(v):
    return int(v, 0) if isinstance(v, str) else int(v)
