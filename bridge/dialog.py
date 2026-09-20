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


def decode_charcodes(b):
    """decode a bytes buffer as u16 charcode stream -> printable text"""
    out = []
    for o in range(0, len(b) - 1, 2):
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
            self.prev = bytes(self.app.emu.memory.read(SCAN_LO, SCAN_HI, 1, False))
            self.open_frame = self.app.frame
            self.text = None
        except Exception:
            self.prev = None

    def poll(self):
        """call each snapshot; returns text once decoded (once per dialog)"""
        if self.prev is None or self.text is not None:
            return None
        if self.app.frame - self.open_frame < DECAY_FRAMES:
            return None
        try:
            cur = bytes(self.app.emu.memory.read(SCAN_LO, SCAN_HI, 1, False))
        except Exception:
            self.prev = None
            return None
        best = ""
        for lo, hi in _changed_ranges(self.prev, cur):
            span = cur[max(0, lo - 64):hi + 64]
            # scan inside the changed span for the longest decodable run
            for start in range(0, max(1, len(span) - 4), 2):
                chunk = span[start:]
                t = decode_charcodes(chunk)
                if len(t) > len(best):
                    best = t
                if len(best) > 12 and (EOS * 2) in chunk[:8]:
                    break
        self.text = best if len(best) >= 4 else None
        self.prev = None
        return self.text
