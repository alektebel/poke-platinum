"""Deterministic screen parsing (#3): what is on the composite frame.

Composite layout: 256xH (H is 384 or 388 depending on capture); top screen is
rows 0..H/2-1, then a small black band, bottom (touch) screen starts at
H-192. Touch coords: y = row - (H-192).
"""
import statistics


def _bands(img):
    h = img.height
    half = h // 2
    return {"top_dialog": (half - 46, half - 2), "bottom_start": h - 192}


def _runs_white(img, rows, x0=8, x1=248, thresh=12):
    """count mostly-white rows in a band"""
    px = img.load()
    white_rows = 0
    y0, y1 = max(0, rows[0]), min(img.height, rows[1])
    for y in range(y0, y1, 2):
        white = sum(1 for x in range(x0, x1, 8)
                    if (lambda c: c[0] > 195 and c[1] > 195 and c[2] > 185)(px[x, y]))
        if white > thresh:
            white_rows += 1
    return white_rows


def _buttons(img, y0):
    """red/blue touch buttons on bottom screen -> centroids (touch coords)"""
    px = img.load()
    reds, blues = [], []
    for y in range(y0, img.height, 2):
        for x in range(0, img.width, 2):
            r, g, b = px[x, y]
            if r > 180 and 60 < g < 130 and b < 110:
                reds.append((x, y - y0))
            elif r < 110 and 90 < g < 160 and b > 170:
                blues.append((x, y - y0))
    out = {}
    if 10 < len(reds) < 800:
        out["red"] = (int(statistics.mean(p[0] for p in reds)), int(statistics.mean(p[1] for p in reds)))
    if len(blues) > 10:
        out["blue"] = (int(statistics.mean(p[0] for p in blues)), int(statistics.mean(p[1] for p in blues)))
    return out


def _hp_bars(img, y0):
    """green/yellow/red horizontal bars on bottom screen (battle UI)"""
    px = img.load()
    rows = 0
    for y in range(y0, img.height, 2):
        green = yellow = red = 0
        for x in range(0, img.width, 2):
            r, g, b = px[x, y]
            if g > 170 and r < 150 and b < 110:
                green += 1
            elif g > 180 and r > 180 and b < 120:
                yellow += 1
            elif r > 190 and g < 110 and b < 110:
                red += 1
        if green + yellow + red > 20:
            rows += 1
    return rows


def parse(img):
    """img: PIL RGB composite. Returns screen-state dict."""
    b = _bands(img)
    out = {}
    out["message_box"] = _runs_white(img, b["top_dialog"]) >= 3
    btns = _buttons(img, b["bottom_start"])
    out["touch_buttons"] = btns
    out["yes_no"] = "red" in btns and "blue" in btns
    bars = _hp_bars(img, b["bottom_start"])
    out["hp_bars"] = bars
    out["battle"] = bars >= 3
    if out["battle"]:
        out["yes_no"] = False
    return out
