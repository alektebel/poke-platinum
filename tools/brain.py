#!/usr/bin/env python3
"""System 2 harness for jev: sense -> decide -> command loop.

The real System 2 is an LLM; this is its deterministic stand-in so the
dashboard shows a live System 1 / System 2 loop. It models the same
contract an LLM brain would use: poll sensors (/state, /memory),
declare goals (set_goal / goal=), dispatch System 1 controllers,
then watch their progress on /telemetry.
"""
import argparse
import json
import random
import sys
import time
from collections import deque

sys.path.insert(0, ".")
from tools.play import cmd, get  # noqa: E402

MAIN_GOAL = "Get out of the house and start the Pokémon journey"
# High-level phase per situation. System 2 thinks in objectives; System 1
# gets the per-tile subgoals. Unknown maps fall back to generic exploration.
PHASES = {
    415: "Leave the bedroom — reach the stairs down",
    414: "Exit the house through the front door",
    411: "Cross Twinleaf Town and leave via the north exit",
    17: "Cross Twinleaf Town and leave via the north exit",
    18: "Cross Twinleaf Town and leave via the north exit",
}
DIRS = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}
DIR_ORDER = list(DIRS)
# yes/no boxes: confirm the ones that advance the mission (starter selection),
# cancel menus/opened UI. Matches against the latched dialog text.
CONFIRM_HINTS = ("pok", "starter", "partner", "briefcase")


def phase_for(map_id):
    return PHASES.get(map_id, f"Explore map {map_id}: cover new tiles and find every exit")


def jget(path, timeout=10):
    return json.loads(get(path, timeout=timeout))


def valid_map(mid):
    return isinstance(mid, int) and 0 <= mid < 100000


def bfs_frontier(map_id, player, mem, avoid=(), ignore_walls=False):
    """BFS from the player through visited tiles only (walls are edges).
    Returns (nearest_reachable_frontier_tile, frontier_count)."""
    m = mem["maps"].get(str(map_id), {})
    visited = {tuple(int(v) for v in t.split(",")) for t in m.get("visited", [])}
    avoid = set(avoid)
    walls = set() if ignore_walls else set(m.get("walls", []))
    start = (player[0], player[1])
    seen = {start}
    queue = deque([start])
    nearest = None
    count = 0
    while queue:
        cur = queue.popleft()
        for d, (dx, dz) in DIRS.items():
            n = (cur[0] + dx, cur[1] + dz)
            if n in seen or n in avoid or f"{cur[0]},{cur[1]},{d}" in walls:
                continue
            if n not in visited:
                count += 1
                if nearest is None:
                    nearest = n
                continue  # frontier tiles are endpoints, not routes
            seen.add(n)
            queue.append(n)
    return nearest, count


def choose_target(map_id, player, mem, avoid=(), ignore_walls=False):
    """Nearest reachable frontier tile (see bfs_frontier). Falls back to a
    random probe ring around the player when the visited graph has no
    reachable frontier."""
    nearest, _ = bfs_frontier(map_id, player, mem, avoid, ignore_walls)
    if nearest is not None:
        return nearest

    m = mem["maps"].get(str(map_id), {})
    visited = {tuple(int(v) for v in t.split(",")) for t in m.get("visited", [])}
    avoid = set(avoid)
    px, pz = player
    for r in range(2, 25):  # nothing adjacent: probe outward
        ring = [(px + dx, pz + dz) for dx in range(-r, r + 1) for dz in range(-r, r + 1)
                if max(abs(dx), abs(dz)) == r and (px + dx, pz + dz) not in visited | avoid]
        if ring:
            return random.choice(ring)
    return None


def warp_target(map_id, player, mem):
    """Nearest known warp tile of this map — used when the current map has
    no reachable frontier left: stepping on the warp transitions maps.
    Prefers the warp whose destination map is the least explored."""
    warps = (mem["maps"].get(str(map_id), {}).get("warps") or {})
    if not warps:
        return None
    px, pz = player
    def rank(item):
        k, dst = item
        tx, tz = int(k.split(",")[0]), int(k.split(",")[1])
        dst_visited = len(mem["maps"].get(str(dst), {}).get("visited", []))
        return (dst_visited, abs(tx - px) + abs(tz - pz))
    k, _ = min(warps.items(), key=rank)
    return (int(k.split(",")[0]), int(k.split(",")[1]))


def wait_controller(timeout=620):
    """Block until System 1 is idle again (poll /telemetry)."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        tel = jget("/telemetry")
        if tel.get("system1", {}).get("controller") is None:
            return True
        time.sleep(0.5)
    return False


def main():
    ap = argparse.ArgumentParser(description="deterministic System 2 harness")
    ap.add_argument("--turbo", action="store_true", help="request emulator turbo")
    ap.add_argument("--max-walk", type=int, default=2400, help="frames per walk goal")
    ap.add_argument("--steps", type=int, default=0, help="stop after N goals (0 = forever)")
    args = ap.parse_args()

    if args.turbo:
        cmd({"action": "turbo", "on": True})

    cmd({"action": "set_goal", "text": MAIN_GOAL})
    print(f"[brain] mission: {MAIN_GOAL}")
    last_map = None
    last_walk = None  # (map, x, z) of the previous walk iteration
    no_progress = 0    # consecutive walks that ended on the same tile
    last_cmd = None   # (map, target, probe) of the walk just executed
    failed = {}        # map_id -> targets whose walk ended short (BFS skips them)
    avoid = set()      # (map, x, z) tiles that open menus when stepped on
    stuck = 0          # consecutive menu-ish boxes with no story text
    done = 0

    try:
        while not args.steps or done < args.steps:
            try:
                st = jget("/state")
            except Exception as e:
                print(f"[brain] bridge unreachable ({e}); retrying")
                time.sleep(3)
                continue

            game = st.get("game") or {}
            scr = st.get("screen") or {}
            game_map = (game.get("map") or {})
            mid = game_map.get("id")

            # interrupt 1: battle
            if scr.get("battle"):
                print("[brain] battle detected -> battle_fight")
                cmd({"action": "set_goal", "text": "Win the wild battle"})
                cmd({"action": "battle_fight", "max_frames": 7200}, timeout=650)
                wait_controller()
                cmd({"action": "set_goal", "text": MAIN_GOAL})
                done += 1
                continue

            # interrupt 2: choice box -> confirm mission-critical prompts,
            # B cancels menus (PC etc.)
            if scr.get("yes_no"):
                text = (game.get("dialog") or "").lower()
                confirm = any(h in text for h in CONFIRM_HINTS)
                if confirm:
                    print(f"[brain] choice box -> YES (dialog: {text[:60]!r})")
                    cmd({"action": "tap", "key": "A", "frames": 6, "post_frames": 25,
                         "goal": "confirm the choice prompt"})
                else:
                    print("[brain] choice box -> B (cancel)")
                    cmd({"action": "tap", "key": "B", "frames": 6, "post_frames": 25,
                         "goal": "cancel the choice prompt"})
                time.sleep(1.0)
                done += 1
                continue

            # interrupt 3: message box
            if scr.get("message_box"):
                if game.get("dialog") or stuck < 2:
                    print("[brain] dialog open -> advance_dialog")
                    cmd({"action": "advance_dialog", "max_taps": 40,
                         "goal": "clear the dialog"}, timeout=650)
                    wait_controller(timeout=120)
                    stuck = 0 if game.get("dialog") else stuck + 1
                else:
                    # menu UI opened by stepping on an object: B out + avoid tile
                    pos = (mid, game_map.get("x"), game_map.get("z"))
                    print(f"[brain] menu loop at {pos} -> B and avoid tile")
                    for _ in range(3):
                        cmd({"action": "tap", "key": "B", "frames": 6, "post_frames": 25,
                             "goal": "close the menu"})
                    avoid.add(pos)
                    stuck = 0
                done += 1
                continue
            stuck = 0

            # in overworld: pick the next exploration goal
            player = (game.get("player") or game_map)
            if not valid_map(mid) or player.get("x") is None:
                time.sleep(1.0)
                continue

            if mid != last_map:
                last_map = mid
                phase = phase_for(mid)
                cmd({"action": "set_goal", "level": "phase",
                     "note": f"phase/map {mid}", "text": phase})
                print(f"[brain] new map {mid} at ({player['x']},{player['z']}) -> phase: {phase}")

            mem = jget("/memory")

            # stuck detection: same tile as the previous walk iteration
            if last_walk == (mid, player["x"], player["z"]):
                no_progress += 1
            else:
                no_progress = 0
            last_walk = (mid, player["x"], player["z"])

            # classify the previous walk: short of target -> remember it as
            # failed so the BFS offers other frontiers; a successful probe
            # means the wall map was too pessimistic -> forget failures
            if last_cmd:
                lm, lt, lprobe = last_cmd
                arrived = lm == mid and (player["x"], player["z"]) == lt
                if not arrived and not lprobe:
                    failed.setdefault(lm, set()).add(lt)
                elif arrived and lprobe:
                    failed.pop(lm, None)
                last_cmd = None
            probe = no_progress >= 4
            if probe:
                no_progress = 0
                print("[brain] 4 walks without movement -> probing past learned walls")

            target, frontier_n = bfs_frontier(mid, (player["x"], player["z"]), mem,
                                              avoid={(x, z) for (m, x, z) in avoid if m == mid}
                                              | failed.get(mid, set()),
                                              ignore_walls=probe)
            if probe:
                # probing: ring probe (walls ignored) to shake off false walls
                target = choose_target(mid, (player["x"], player["z"]), mem,
                                       avoid={(x, z) for (m, x, z) in avoid if m == mid}
                                       | failed.get(mid, set()),
                                       ignore_walls=True)
            via_warp = False
            if target is None:
                w = warp_target(mid, (player["x"], player["z"]), mem)
                if w is not None:
                    target = w
                    via_warp = True
                    print(f"[brain] map {mid} exhausted -> heading to warp {target}")
            if target is None:
                print("[brain] map fully explored, no known warps; waiting")
                time.sleep(5)
                continue

            tx, tz = target
            frames = 600 if probe else args.max_walk
            print(f"[brain] goal: walk ({player['x']},{player['z']}) -> ({tx},{tz})"
                  + (" [probe]" if probe else ""))
            r = cmd({"action": "walk_to", "x": tx, "z": tz,
                     "max_frames": frames,
                     "ignore_walls": probe,
                     "goal": f"walk to ({tx},{tz}) on map {mid}"}, timeout=650)
            wait_controller(timeout=frames / 30 + 30)
            last_cmd = (mid, (tx, tz), probe)
            print(f"[brain] walk done: {json.dumps(r)}")
            done += 1
    except KeyboardInterrupt:
        pass
    finally:
        cmd({"action": "release_all"})
        print(f"[brain] stopped after {done} goals")


if __name__ == "__main__":
    main()
