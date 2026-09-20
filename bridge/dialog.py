"""Dialog text extraction: diff the heap when a message box opens, decode charcode.

The message system copies the formatted string into a heap buffer; we snapshot
the region on dialog_open, diff ~2s later (after typing), and decode the best
u16 charcode run found. Self-calibrating: no hardcoded buffer address.
"""
import json
import os
import time

SCAN_LO, SCAN_HI = 0x02240000, 0x02400000
DECAY_FRAMES = 240  # frames to wait so typing finishes

_DIR = os.path.dirname(os.path.abspath(__file__))
CHARMAP = {int(k): v for k, v in json.load(open(os.path.join(_DIR, "charmap.json"))).items()}
EOS = 0xFFFF


def _u16(b, o):
    return int.from_bytes(b[o:o + 2], "little")


def decode_charcodes(b, max_chars=300):
    """decode a bytes buffer as u16 charcode stream -> printable text"""
    out = []
    for o in range(0, min(len(b) - 1, max_chars * 2), 2):
        v = _u16(b, o)
        if v == EOS:
            break
        c = CHARMAP.get(v)
        if c is None:
            if out and out[-1] != " ":
                out.append(" ")
        else:
            out.append(c)
    return "".join(out).strip()


def _changed_ranges(a, b):
    out = []
    i = 0
    n = min(len(a), len(b))
    while i < n:
        if a[i:i + 2] != b[i:i + 2]:
            j = i
            while j < n and a[j:j + 2] != b[j:j + 2]:
                j += 2
            out.append((i, j))
            i = j
        else:
            i += 2
    return out


class DialogReader:
    """Latched reader: snapshot on open, decode after DECAY_FRAMES."""

    def __init__(self, app):
        self.app = app
        self.prev = None
        self.open_frame = None
        self.text = None

    def on_open(self):
        try:
            prev = bytes(self.app.emu.memory.read(SCAN_LO, SCAN_HI, 1, False))
            self.prev = prev
            self.open_frame = self.app.frame
            self.text = None
        except Exception:
            self.prev = None

    def poll(self):
        """call each snapshot; returns text once decoded (once per dialog).

        Thread-safe against concurrent snapshot() calls: works on local
        copies so a sibling poll() resetting self.prev can't crash us.
        """
        prev, open_frame = self.prev, self.open_frame
        if prev is None or self.text is not None or open_frame is None:
            return None
        if self.app.frame - open_frame < DECAY_FRAMES:
            return None
        try:
            cur = bytes(self.app.emu.memory.read(SCAN_LO, SCAN_HI, 1, False))
        except Exception:
            self.prev = None
            return None
        best = ""
        for lo, hi in _changed_ranges(prev, cur):
            if hi - lo > 1 << 16:
                continue  # huge heap shift (scene load), not dialog typing
            span = cur[max(0, lo - 512):hi + 64][:8192]
            # find candidate string starts: offsets where 2+ consecutive
            # u16s decode to real chars (skips garbage prefixes fast)
            for start in range(0, len(span) - 8, 2):
                if CHARMAP.get(_u16(span, start)) is None:
                    continue
                if CHARMAP.get(_u16(span, start + 2)) is None and \
                   CHARMAP.get(_u16(span, start + 4)) is None:
                    continue
                t = decode_charcodes(span[start:])
                if len(t) > len(best):
                    best = t
                if len(best) > 12 and b"\xff\xff" in span[start:start + 8]:
                    break
            if len(best) > 12:
                break
        self.text = best if len(best) >= 4 else None
        self.prev = None
        return self.text
