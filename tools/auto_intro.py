#!/usr/bin/env python3
"""Auto-advance the intro: touch YES/NO prompts, mash A otherwise."""
import io
import json
import sys
import urllib.request

sys.path.insert(0, ".")
from tools.play import cmd, get, shot  # noqa: E402

from PIL import Image  # noqa: E402


def find_button(img, want):
    """Find YES (red) or NO (blue) button in the bottom half of the composite."""
    w, h = img.size
    half = h // 2
    bottom = img.crop((0, half, w, h))
    px = bottom.load()
    reds, blues = [], []
    for y in range(0, bottom.height, 2):
        for x in range(0, bottom.width, 2):
            r, g, b = px[x, y]
            if r > 180 and 60 < g < 130 and b < 110:
                reds.append((x, y))
            elif r < 110 and 90 < g < 160 and b > 170:
                blues.append((x, y))
    import statistics
    if want == "yes" and len(reds) > 20:
        return (int(statistics.mean(p[0] for p in reds)), int(statistics.mean(p[1] for p in reds)))
    if want == "no" and len(blues) > 20:
        return (int(statistics.mean(p[0] for p in blues)), int(statistics.mean(p[1] for p in blues)))
    return None


def main():
    rounds = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    for i in range(rounds):
        img = Image.open(io.BytesIO(get("/screen")))
        w, h = img.size
        pos = find_button(img, "yes")
        if pos:
            bx, by = pos
            print(f"[{i}] touching YES at bottom ({bx},{by})")
            cmd({"action": "touch", "x": bx, "y": by})
            cmd({"action": "wait", "frames": 15})
            cmd({"action": "touch_release"})
            cmd({"action": "wait", "frames": 40})
        else:
            cmd({"action": "tap", "key": "A", "frames": 2, "post_frames": 12})
    shot("/tmp/opencode/auto_end.png")
    print("done; saved /tmp/opencode/auto_end.png")


if __name__ == "__main__":
    main()
