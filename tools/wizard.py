#!/usr/bin/env python3
"""Finish the new-game wizard: navigate menus, answer touch prompts, mash A."""
import io
import sys
import warnings

warnings.filterwarnings("ignore")
sys.path.insert(0, ".")
from tools.play import cmd, get, shot  # noqa: E402
from tools.auto_intro import find_button  # noqa: E402
from PIL import Image  # noqa: E402


def menu_visible(img):
    """The 3-choice info menu: blue-bordered box at top-left of top screen."""
    crop = img.convert("RGB").crop((10, 4, 120, 40))
    px = list(crop.getdata())
    dark = sum(1 for r, g, b in px if r < 60 and g < 80 and b < 140)
    return dark > 60


def gender_screen(img):
    w, h = img.size
    bottom = img.convert("RGB").crop((0, h // 2, w, h))
    px = list(bottom.getdata())
    light = sum(1 for r, g, b in px if r > 210 and g > 210 and b > 210)
    return light / len(px) > 0.35


def main():
    max_rounds = int(sys.argv[1]) if len(sys.argv) > 1 else 120
    for i in range(max_rounds):
        img = Image.open(io.BytesIO(get("/screen")))
        if gender_screen(img):
            img.save("/tmp/opencode/GENDER.png")
            print("GENDER SCREEN DETECTED at round", i)
            return
        yes = find_button(img, "yes")
        if yes:
            cmd({"action": "touch", "x": yes[0], "y": yes[1]})
            cmd({"action": "wait", "frames": 12})
            cmd({"action": "touch_release"})
            cmd({"action": "wait", "frames": 45})
            continue
        if menu_visible(img):
            print(f"[{i}] menu -> NO INFO NEEDED")
            cmd({"action": "tap", "key": "DOWN", "frames": 2, "post_frames": 18})
            cmd({"action": "tap", "key": "DOWN", "frames": 2, "post_frames": 18})
            cmd({"action": "tap", "key": "A", "frames": 2, "post_frames": 60})
            continue
        cmd({"action": "tap", "key": "A", "frames": 2, "post_frames": 65})
    shot("/tmp/opencode/wizard_end.png")
    print("rounds exhausted; saved /tmp/opencode/wizard_end.png")


if __name__ == "__main__":
    main()
