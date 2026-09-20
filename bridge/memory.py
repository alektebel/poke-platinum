"""Episodic memory + atlas (#5): events, visited tiles, learned walls, warps."""
import json
import os
import threading
import time
from collections import deque

DIRS = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}


class Memory:
    def __init__(self, path):
        self.path = path
        self.lock = threading.RLock()
        self.events = deque(maxlen=1000)
        self.event_seq = 0
        self.data = {"maps": {}, "notes": []}
        self.load()

    def load(self):
        if os.path.exists(self.path):
            try:
                self.data = json.load(open(self.path))
            except Exception:
                pass

    def save(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self.data, f, indent=1)
        os.replace(tmp, self.path)

    def _map(self, map_id):
        return self.data["maps"].setdefault(str(map_id), {"visited": [], "walls": [], "warps": {}})

    def event(self, kind, **kw):
        with self.lock:
            self.events.append({"seq": self.event_seq, "frame": time.time(), "kind": kind, **kw})
            self.event_seq += 1
            self.save()

    def events_since(self, since):
        return [e for e in self.events if e["seq"] > since]

    def visit(self, map_id, x, z):
        m = self._map(map_id)
        tile = f"{x},{z}"
        with self.lock:
            if tile not in m["visited"]:
                m["visited"].append(tile)
                self.save()

    def learn_wall(self, map_id, x, z, facing):
        m = self._map(map_id)
        wall = f"{x},{z},{facing}"
        with self.lock:
            if wall not in m["walls"]:
                m["walls"].append(wall)
                self.save()
                self.event("wall_learned", map=map_id, x=x, z=z, dir=facing)

    def learn_warp(self, from_map, x, z, to_map):
        m = self._map(from_map)
        with self.lock:
            m["warps"][f"{x},{z}"] = to_map
            self.save()
            self.event("warp_learned", src=from_map, x=x, z=z, dst=to_map)

    def note(self, text):
        with self.lock:
            self.data["notes"].append({"t": time.time(), "text": text})
            self.save()
            self.event("note", text=text)

    def snapshot(self):
        return {"maps": self.data["maps"], "notes": self.data["notes"],
                "recent_events": list(self.events)[-50:]}
