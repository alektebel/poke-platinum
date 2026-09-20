"""Live telemetry for the dashboard: System 2 goals, jev's actions, System 1 state.

In-memory only (session-scoped). Thread-safe: written from HTTP threads,
read by the /telemetry poller.
"""
import threading
import time
from collections import deque

CONTROLLER_ACTIONS = {"advance_dialog", "walk_to", "menu_navigate", "battle_fight"}

# attributes worth exposing from any live controller
_CTRL_ATTRS = ("ticks", "phase", "hold_dir", "origin", "fail", "taps", "taps_max",
               "done", "count", "dir", "confirm", "target", "move_index",
               "max_frames", "max_taps", "cooldown", "menu_seen")


class Telemetry:
    def __init__(self):
        self.lock = threading.RLock()
        self.seq = 0
        self.main_goal = None      # {"text", "note", "t", "seq"}
        self.goals = deque(maxlen=50)    # goal history
        self.actions = deque(maxlen=300)  # every /command jev executed
        self._prev_ctrl = None     # name of controller seen on last update()

    def set_goal(self, text, note=None, main=True):
        if not isinstance(text, str) or not text.strip():
            return None
        with self.lock:
            entry = {"seq": self.seq, "t": time.time(), "text": text.strip(),
                     "note": note, "main": main}
            self.seq += 1
            if main:
                self.main_goal = entry
            self.goals.appendleft(entry)
        return entry

    def record_action(self, body, result):
        if not isinstance(body, dict):
            return
        action = body.get("action")
        if action == "set_goal":   # goals surface in the goal panel instead
            return
        with self.lock:
            entry = {"seq": self.seq, "t": time.time(), "action": action,
                     "input": body, "result": result}
            self.seq += 1
            self.actions.appendleft(entry)

    # -- System 1 introspection -------------------------------------------
    @staticmethod
    def describe_controller(ctrl):
        d = {"name": ctrl.name, "ticks": getattr(ctrl, "ticks", 0)}
        for attr in _CTRL_ATTRS:
            v = getattr(ctrl, attr, None)
            if v is not None and attr != "ticks":
                d[attr] = v
        # progress estimate: fraction of budget consumed
        cap = getattr(ctrl, "max_frames", None) or getattr(ctrl, "max_taps", None)
        if cap:
            d["progress"] = round(min(d["ticks"] / cap, 1.0), 3)
        else:
            count, total = getattr(ctrl, "done", None), getattr(ctrl, "count", None)
            if isinstance(count, int) and isinstance(total, int) and total > 0:
                d["progress"] = round(min(count / total, 1.0), 3)
        return d

    def update(self, app):
        """Poll live System 1 state; emits synthetic actions on start/finish."""
        ctrl = app.controller
        with self.lock:
            name = ctrl.name if ctrl is not None else None
            if self._prev_ctrl is not None and name != self._prev_ctrl:
                self.actions.appendleft({
                    "seq": self.seq, "t": time.time(), "action": "_controller_done",
                    "input": {"controller": self._prev_ctrl},
                    "result": {"ok": True, "note": f"{self._prev_ctrl} finished/aborted"},
                })
                self.seq += 1
            self._prev_ctrl = name
            state = self.describe_controller(ctrl) if ctrl is not None else None
        return {"controller": state, "keypad": app.keypad, "turbo": app.turbo}

    def snapshot(self, app=None):
        system1 = self.update(app) if app is not None else {"controller": None}
        with self.lock:
            return {
                "t": time.time(),
                "main_goal": self.main_goal,
                "goals": list(self.goals)[:12],
                "actions": list(self.actions)[:80],
                "system1": system1,
            }
