#!/usr/bin/env python3
"""Intro driver v3: verified menu navigation, proper touch, state logging."""
import io
import statistics
import sys
import time

sys.path.insert(0, ".")
from tools.play import cmd, get  # noqa: E402
from PIL import Image  # noqa: E402

YES_TOUCH = (119, 85)


def screen():
    return Image.open(io.BytesIO(get("/screen"))).convert("RGB")


def buttons(img):
    px = img.load()
    reds, blues = [], []
    for y in range(196, 388, 2):
        for x in range(0, 256, 2):
            r, g, b = px[x, y]
            if r > 180 and 60 < g < 130 and b < 110:
                reds.append((x, y - 196))
            elif r < 110 and 90 < g < 160 and b > 170:
                blues.append((x, y - 196))
    out = {}
    if 10 < len(reds) < 800 and len(blues) > 10:
        out["yes"] = (int(statistics.mean(p[0] for p in reds)), int(statistics.mean(p[1] for p in reds)))
    return out


def is_topic_menu(img):
    """White box, dark text, in the top-left of the top screen (y 20-75)."""
    crop = img.crop((8, 20, 118, 76))
    px = [crop.getpixel((x, y)) for y in range(0, crop.height, 2) for x in range(0, crop.width, 2)]
    white = sum(1 for r, g, b in px if r > 210 and g > 210 and b > 210)
    dark = sum(1 for r, g, b in px if r < 70 and g < 70 and b < 90)
    return white > 400 and 40 < dark < 600


def cursor_row(img):
    """Cursor arrow column x~8-16; rows ~31/47/63."""
    for y in range(24, 72):
        for x in range(4, 18):
            r, g, b = img.getpixel((x, y))
            if r < 70 and g < 70 and b < 90:
                return y
    return None


def top_kind(img):
    px = [img.getpixel((x, y)) for y in range(90, 182, 8) for x in range(90, 246, 12)]
    n = len(px)
    blue = sum(1 for r, g, b in px if b > 120 and b > r + 30) / n
    light = sum(1 for r, g, b in px if r > 170 and g > 155 and b < 230) / n
    white = sum(1 for r, g, b in px if r > 225 and g > 225 and b > 225) / n
    if blue > 0.6:
        return "blue"
    if light > 0.5:
        return "tan"
    if white > 0.6:
        return "white"
    return "other"


def touch(x, y, hold=70):
    cmd({"action": "touch", "x": x, "y": y})
    cmd({"action": "wait", "frames": hold})
    cmd({"action": "touch_release"})
    cmd({"action": "wait", "frames": 70})


def tap(key, f=10, post=40):
    cmd({"action": "tap", "key": key, "frames": f, "post_frames": post})


def pick_no_info_needed():
    cmd({"action": "wait", "frames": 40})
    # cursor starts at CONTROL INFO (row ~31); move to NO INFO NEEDED (row ~63)
    for _ in range(2):
        for _try in range(4):
            y0 = cursor_row(screen())
            tap("DOWN", 10, 35)
            y1 = cursor_row(screen())
            if y0 is not None and y1 is not None and abs(y1 - y0) >= 12:
                break
        time.sleep(0.05)
    tap("A", 10, 60)


def main():
    max_steps = int(sys.argv[1]) if len(sys.argv) > 1 else 600
    log = open("/tmp/opencode/jev/driver3.log", "w")
    last_st = None
    menus = 0
    for i in range(max_steps):
        img = screen()
        bs = buttons(img)
        if is_topic_menu(img):
            st = "menu"
        elif bs:
            st = "buttons"
        else:
            st = top_kind(img)
        log.write(f"{i}: {st} {bs} cur={cursor_row(img) if st == 'menu' else ''}\n")
        log.flush()
        if st != last_st:
            img.save(f"/tmp/opencode/jev/d3_{st}_{i}.png")
            last_st = st
        if st == "menu":
            pick_no_info_needed()
            menus += 1
        elif st == "buttons":
            touch(*bs.get("yes", YES_TOUCH))
        elif st in ("blue", "tan", "other"):
            tap("A", 10, 45)
        elif st == "white":
            cmd({"action": "wait", "frames": 90})
            img2 = screen()
            if top_kind(img2) == "white":
                img2.save("/tmp/opencode/jev/GENDER.png")
                print("WHITE SCREEN (gender?) at step", i)
                return
        time.sleep(0.03)
    img = screen()
    img.save("/tmp/opencode/jev/driver3_end.png")
    print("final:", st, "menus:", menus)


if __name__ == "__main__":
    main()
