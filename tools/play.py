#!/usr/bin/env python3
"""play.py — thin CLI client for the jev-platinum bridge."""
import io
import json
import sys
import time
import urllib.request

BASE = "http://127.0.0.1:7790"


def cmd(body, timeout=30):
    req = urllib.request.Request(BASE + "/command", json.dumps(body).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def get(path, timeout=10):
    with urllib.request.urlopen(BASE + path, timeout=timeout) as r:
        return r.read()


def state():
    return json.loads(get("/state"))


def shot(path, part="both"):
    from PIL import Image
    img = Image.open(io.BytesIO(get(f"/screen?part={part}")))
    img.save(path)
    return path


def mash(key, n, gap=12, shot_every=None, shot_part="both", shot_prefix="/tmp/opencode/mash"):
    for i in range(n):
        r = cmd({"action": "tap", "key": key, "frames": 2, "post_frames": gap})
        if r.get("ok") is False:
            print("cmd error:", r)
            return
        if shot_every and (i + 1) % shot_every == 0:
            p = f"{shot_prefix}_{i:04d}.png"
            shot(p, shot_part)
            print(f"[{i+1}/{n}] {p}")
    print("done", n, "taps")


def main():
    if len(sys.argv) < 2:
        print("usage: play.py cmd|state|shot|mash ...")
        return
    what = sys.argv[1]
    if what == "cmd":
        print(cmd(json.loads(sys.argv[2]), timeout=float(sys.argv[3]) if len(sys.argv) > 3 else 30))
    elif what == "state":
        print(json.dumps(state(), indent=1))
    elif what == "shot":
        part = sys.argv[3] if len(sys.argv) > 3 else "both"
        print(shot(sys.argv[2], part))
    elif what == "mash":
        key = sys.argv[2] if len(sys.argv) > 2 else "A"
        n = int(sys.argv[3]) if len(sys.argv) > 3 else 10
        gap = int(sys.argv[4]) if len(sys.argv) > 4 else 12
        mash(key, n, gap=gap, shot_every=max(1, n // 6))
    elif what == "wait":
        print(cmd({"action": "wait", "frames": int(sys.argv[2])}, timeout=60))


if __name__ == "__main__":
    main()
