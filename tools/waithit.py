#!/usr/bin/env python3
"""Poll /screen, detect a phase by pixel signature, then act. System-1 prototype."""
import io
import json
import sys
import urllib.request

BASE = "http://127.0.0.1:7790"


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=10) as r:
        return r.read()


def cmd(body, timeout=30):
    req = urllib.request.Request(BASE + "/command", json.dumps(body).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def shot(part):
    from PIL import Image
    return Image.open(io.BytesIO(get(f"/screen?part={part}"))).convert("RGB")


def classify_title(img):
    w, h = img.size
    band = img.crop((w // 4, int(h * 0.55), 3 * w // 4, int(h * 0.75)))
    px = list(band.getdata())
    bright = sum(1 for r, g, b in px if r > 180 and g > 180 and b > 180)
    red = sum(1 for r, g, b in px if r > 140 and g < 90 and b < 90)
    n = len(px)
    if bright / n > 0.5 and red / n > 0.02:
        return "press_start"
    if bright / n > 0.5:
        return "white_title"
    return None


def wait_for(check, max_frames=3600, poll=30, name="phase"):
    waited = 0
    while waited < max_frames:
        cmd({"action": "wait", "frames": poll})
        waited += poll
        img = shot("top")
        state = check(img)
        if state:
            print(f"[{name}] detected after {waited} frames")
            return state
    print(f"[{name}] timeout")
    return None


def main():
    state = wait_for(classify_title, name="title")
    if state in ("press_start", "white_title"):
        cmd({"action": "tap", "key": "START", "frames": 4, "post_frames": 90})
        cmd({"action": "wait", "frames": 60})
        shot("both").save("/tmp/opencode/after_start.png")
        print("pressed START at title; saved /tmp/opencode/after_start.png")


if __name__ == "__main__":
    main()
