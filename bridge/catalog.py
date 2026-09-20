CATALOG = {
    "version": 1,
    "primitives": {
        "tap": {"params": {"key": "A|B|X|Y|L|R|START|SELECT|UP|DOWN|LEFT|RIGHT", "frames": "1-30, default 2"}},
        "press": {"params": {"keys": ["A", "B"], "frames": "default 2"}},
        "hold": {"params": {"key": "..."}},
        "release": {"params": {"key": "..."}},
        "release_all": {},
        "touch": {"params": {"x": "0-255", "y": "0-191"}},
        "touch_release": {},
        "wait": {"params": {"frames": "1-3600"}},
        "reset": {},
        "savestate": {"params": {"file": "path"}},
        "loadstate": {"params": {"file": "path"}},
        "turbo": {"params": {"on": "bool"}},
    },
    "goals": {
        "advance_dialog": {"params": {"max_taps": "1-300, default 60"}, "note": "mashes A to advance/complete dialog"},
        "walk_to": {"params": {"x": "int", "y": "int"}, "note": "grid pathfind to tile (needs sensor)"},
        "menu_navigate": {"params": {"dir": "up|down|left|right", "count": "int", "confirm": "bool"}},
        "battle_choice": {"params": {"kind": "move|switch|item|run", "index": "0-3"}},
        "stop_goal": {},
    },
    "reads": {
        "GET /state": "full JSON game snapshot",
        "GET /ping": "liveness + fps",
        "GET /screen?part=top|bottom": "PNG frame",
    },
}
