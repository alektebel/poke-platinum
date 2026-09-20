#!/usr/bin/env python3
"""Calibrate pokeplatinum RAM map via the bridge /mem endpoint."""
import json
import sys

sys.path.insert(0, ".")
from tools.play import cmd, get  # noqa: E402

RAM_START = 0x02000000
RAM_END = 0x02400000
CHUNK = 1 << 18  # 256KB per call


def read_ram(start=RAM_START, end=RAM_END):
    out = bytearray()
    a = start
    while a < end:
        n = min(CHUNK, end - a)
        r = json.loads(get(f"/mem?addr={hex(a)}&len={n}", timeout=30))
        out += bytes.fromhex(r["hex"])
        a += n
    return bytes(out)


def u32(b, off):
    return int.from_bytes(b[off:off + 4], "little")


def s32(b, off):
    v = u32(b, off)
    return v - 0x100000000 if v >= 0x80000000 else v


def find_map_objects(ram):
    hits = []
    for base in range(0, len(ram) - 0xB0, 4):
        off = RAM_START + base
        x = s32(ram, base + 0x64)
        z = s32(ram, base + 0x6C)
        px = u32(ram, base + 0x70)
        pz = u32(ram, base + 0x78)
        facing = s32(ram, base + 0x28)
        if not (0 <= x < 512 and 0 <= z < 512):
            continue
        if px != ((x << 16) | 0x8000) or pz != ((z << 16) | 0x8000):
            continue
        if not (0 <= facing <= 3):
            continue
        status = u32(ram, base)
        if status == 0:
            continue
        hits.append({"addr": hex(off), "x": x, "z": z, "facing": facing,
                     "status": hex(status), "graphicsID": u32(ram, base + 0x10),
                     "movementType": u32(ram, base + 0x14)})
    return hits


def find_refs(ram, target, lo=RAM_START, hi=RAM_END):
    t = target.to_bytes(4, "little")
    hits = []
    i = lo - RAM_START
    while True:
        i = ram.find(t, i)
        if i < 0 or i + 4 > hi - RAM_START:
            break
        if i % 4 == 0:
            hits.append(RAM_START + i)
        i += 4
    return hits


def main():
    print("reading RAM...")
    ram = read_ram()
    print(f"{len(ram)} bytes")
    mos = find_map_objects(ram)
    print("MapObject candidates:")
    for m in mos:
        print("  ", m)
    json.dump(mos, open("/tmp/opencode/jev/mos.json", "w"))
    return mos


if __name__ == "__main__":
    main()
