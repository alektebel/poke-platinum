"""RAM sensor for pokeplatinum (US rev0). Calibrated against live gameplay.

Pointer chain (all offsets verified in the wild):
  sFieldSystem (static 0x021BF680, alt 0x021C07DC) -> FieldSystem*
  FieldSystem+0x0C -> SaveData*      (+0x1C -> Location*   +0x38 -> MapObjectManager*
                                      +0x3C -> PlayerAvatar*)
  Location:    mapHeaderID@0x00 warpId@0x04 x@0x08 z@0x0C facing@0x10
  PlayerAvatar:+0x20 gender  +0x30 -> MapObject*
  MapObject:   facingDir@0x28  x@0x64  y(height)@0x68  z@0x6C  pos.fx32@0x70
  MapObjectManager: objectCnt@0x08  player MapObject*@0x124  FieldSystem*@0x128
"""
import time

import bridge.screen_parse as screen_parse
from bridge.dialog import DialogReader

FIELD_SYSTEM_PTRS = (0x021BF680, 0x021C07DC)
SAVE_DATA_PTRS = (0x021C0794, 0x02101D40)

FS_SAVEDATA = 0x0C
FS_LOCATION = 0x1C
FS_MAPOBJMAN = 0x38
FS_AVATAR = 0x3C

AV_GENDER = 0x20
AV_MAPOBJ = 0x30

MO_STATUS = 0x00
MO_LOCALID = 0x08
MO_GRAPHICS = 0x10
MO_FACING = 0x28
MO_X = 0x64
MO_Y = 0x68
MO_Z = 0x6C

MAN_OBJECTCNT = 0x08
MAN_PLAYER = 0x124

LOC_MAP = 0x00
LOC_WARP = 0x04
LOC_X = 0x08
LOC_Z = 0x0C
LOC_FACING = 0x10

FACING_NAMES = ("up", "down", "left", "right")
HEAP_LO, HEAP_HI = 0x02200000, 0x02400000


def _u32(mem, off):
    return int.from_bytes(mem[off:off + 4], "little")


def _s32(mem, off):
    v = _u32(mem, off)
    return v - 0x100000000 if v >= 0x80000000 else v


class Sensor:
    def __init__(self, app):
        self.app = app
        self.t0 = time.time()
        self._prev = {}   # last raw keys for event diffing
        self.dialogs = DialogReader(app)
        self.last_dialog = None

    # -- low level -------------------------------------------------------
    def _read(self, addr, n):
        return bytes(self.app.emu.memory.read(addr, addr + n, 1, False))

    def _field_system(self):
        for ptr in FIELD_SYSTEM_PTRS:
            try:
                fs = _u32(self._read(ptr, 4), 0)
                if HEAP_LO <= fs < HEAP_HI:
                    av = _u32(self._read(fs + FS_AVATAR, 4), 0)
                    if av and HEAP_LO <= av < HEAP_HI:
                        mo = _u32(self._read(av + AV_MAPOBJ, 4), 0)
                        if mo and HEAP_LO <= mo < HEAP_HI:
                            return fs
                    return fs
            except Exception:
                continue
        return None

    # -- fast field probes for controllers (no screen work) --------------
    def field_state(self):
        """(map_id, x, z, facing) or None when not in the overworld."""
        fs = self._field_system()
        if fs is None:
            return None
        try:
            loc = _u32(self._read(fs + FS_LOCATION, 4), 0)
            lb = self._read(loc, 0x14)
            av = _u32(self._read(fs + FS_AVATAR, 4), 0)
            mo = _u32(self._read(av + AV_MAPOBJ, 4), 0)
            mb = self._read(mo, MO_Z + 4)
            return (_s32(lb, LOC_MAP), _s32(mb, MO_X), _s32(mb, MO_Z), _s32(mb, MO_FACING))
        except Exception:
            return None

    def screen_state(self):
        png, _ = self.app.last_png()
        if png is None:
            return {}
        from PIL import Image
        return screen_parse.parse(png.convert("RGB"))

    # -- NPC scan (#1) ----------------------------------------------------
    def npcs(self, radius=48):
        """MapObject-shaped structs in heap near the player (signature scan)."""
        st = self.field_state()
        if st is None:
            return []
        _, px_, pz_, _ = st
        out = []
        data = self._read(HEAP_LO, HEAP_HI - HEAP_LO)
        for base in range(0, len(data) - 0xB0, 4):
            x = _s32(data, base + 0x64)
            z = _s32(data, base + 0x6C)
            pxfx = _u32(data, base + 0x70)
            pzfx = _u32(data, base + 0x78)
            facing = _s32(data, base + 0x28)
            if not (0 <= x < 512 and 0 <= z < 512):
                continue
            if pxfx != ((x << 16) | 0x8000) or pzfx != ((z << 16) | 0x8000):
                continue
            if not (0 <= facing <= 3):
                continue
            status = _u32(data, base)
            if status == 0 or abs(x - px_) > radius or abs(z - pz_) > radius:
                continue
            out.append({"addr": hex(HEAP_LO + base), "x": x, "z": z, "facing": FACING_NAMES[facing],
                        "graphics": _u32(data, base + MO_GRAPHICS), "status": hex(status)})
        return out

    # -- main snapshot -----------------------------------------------------
    def snapshot(self):
        app = self.app
        snap = {
            "frame": app.frame,
            "fps": round(app.fps(), 1),
            "turbo": app.turbo,
            "keypad": app.keypad,
            "controller": app.controller.name if app.controller else None,
            "game": None,
            "screen": self.screen_state(),
        }

        fs = self._field_system()
        if fs is None:
            snap["note"] = "no_field_system (title/menus/non-field scene)"
            self._diff(snap)
            return snap

        game = {"scene": "field"}
        try:
            loc = _u32(self._read(fs + FS_LOCATION, 4), 0)
            lb = self._read(loc, 0x14)
            game["map"] = {
                "id": _s32(lb, LOC_MAP),
                "warp": _s32(lb, LOC_WARP),
                "x": _s32(lb, LOC_X),
                "z": _s32(lb, LOC_Z),
                "facing": FACING_NAMES[_s32(lb, LOC_FACING)] if 0 <= _s32(lb, LOC_FACING) < 4 else _s32(lb, LOC_FACING),
            }
        except Exception:
            game["map"] = None

        try:
            av = _u32(self._read(fs + FS_AVATAR, 4), 0)
            ab = self._read(av, 0x40)
            mo = _u32(ab, AV_MAPOBJ)
            mb = self._read(mo, MO_Z + 4)
            game["player"] = {
                "x": _s32(mb, MO_X),
                "z": _s32(mb, MO_Z),
                "facing": FACING_NAMES[_s32(mb, MO_FACING)] if 0 <= _s32(mb, MO_FACING) < 4 else _s32(mb, MO_FACING),
                "gender": _s32(ab, AV_GENDER),
            }
        except Exception:
            game["player"] = None

        try:
            man = _u32(self._read(fs + FS_MAPOBJMAN, 4), 0)
            cnt = _s32(self._read(man + MAN_OBJECTCNT, 4), 0)
            player_mo = _u32(self._read(man + MAN_PLAYER, 4), 0)
            game["objects"] = {"count": cnt, "player_addr": hex(player_mo)}
        except Exception:
            game["objects"] = None

        game["dialog"] = self.dialogs.text or self.last_dialog

        snap["game"] = game
        snap.pop("note", None)
        self._diff(snap)
        return snap

    # -- event diffing (#4) ------------------------------------------------
    def _diff(self, snap):
        app = self.app
        mem = getattr(app, "memory", None)
        if mem is None:
            return
        game = snap.get("game") or {}
        player = (game.get("player") or {})
        map_ = (game.get("map") or {})
        key_pos = (map_.get("id"), player.get("x"), player.get("z"))
        prev = self._prev

        if key_pos != prev.get("pos") and all(v is not None for v in key_pos):
            if prev.get("pos") and prev["pos"][0] != key_pos[0]:
                mem.event("map_changed", **{"from": prev["pos"][0], "to": key_pos[0],
                                            "x": key_pos[1], "z": key_pos[2]})
                mem.learn_warp(prev["pos"][0], prev["pos"][1], prev["pos"][2], key_pos[0])
            elif prev.get("pos"):
                mem.event("moved", map=key_pos[0],
                          **{"from": list(prev["pos"][1:]), "to": [key_pos[1], key_pos[2]]})
            if all(v is not None for v in key_pos):
                mem.visit(key_pos[0], key_pos[1], key_pos[2])
            prev["pos"] = key_pos

        scr = snap.get("screen") or {}
        if scr.get("battle") != prev.get("battle"):
            mem.event("battle_started" if scr.get("battle") else "battle_ended")
            prev["battle"] = scr.get("battle")
        if scr.get("message_box") != prev.get("dialog"):
            opened = scr.get("message_box")
            mem.event("dialog_opened" if opened else "dialog_closed")
            prev["dialog"] = opened
            if opened:
                self.dialogs.on_open()
            elif self.dialogs.text:
                self.last_dialog = self.dialogs.text
                mem.event("dialog", text=self.last_dialog)
        text = self.dialogs.poll()
        if text and text != self.last_dialog:
            self.last_dialog = text
            mem.event("dialog", text=text)
