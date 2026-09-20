#!/usr/bin/env python3
"""Inspect experiment traces recorded by bridge/experiment.py.

  tools/trace.py list                     all experiments + status
  tools/trace.py summary [exp]            duration, counts, goals, maps, outcome
  tools/trace.py timeline [exp] [-n N]    chronological: goals, commands, key changes
  tools/trace.py commands [exp] [-n N]    the command log (what System 2 sent)
  tools/trace.py path [exp]               visited tiles per map (ASCII grid)
  tools/trace.py report [exp]             self-contained HTML report in the exp dir
  tools/trace.py close [exp]              finalize an experiment killed before finish()
"""
import argparse
import glob
import json
import os
import sys
import time


def latest():
    exps = sorted(glob.glob("experiments/exp_*"))
    return exps[-1] if exps else None


def resolve(exp):
    d = exp or latest()
    if d and not d.startswith("experiments/"):
        d = os.path.join("experiments", d)
    if not d or not os.path.isdir(d):
        sys.exit(f"experiment not found: {exp or '(none)'} — run with --record first")
    return d


def load(exp):
    lines = []
    with open(os.path.join(exp, "trace.jsonl")) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    lines.append(json.loads(line))
                except json.JSONDecodeError:
                    pass  # partial last line of a still-running experiment
    return lines


def hhmmss(t, t0):
    s = int(t - t0)
    return f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}"


def goal_label(g):
    if not g:
        return None
    if g.get("main"):
        return f"MISSION  {g['text']}"
    if str(g.get("note") or "").startswith("phase"):
        return f"phase    {g['text']}"
    return f"sub      {g['text']}"


# ---------------------------------------------------------------- summaries
def cmd_summary(exp):
    lines = load(exp)
    t0 = lines[0]["t"] if lines else 0
    kinds = {}
    for l in lines:
        kinds[l["kind"]] = kinds.get(l["kind"], 0) + 1

    goal_changes, maps, battles, cmds = [], [], [], [l for l in lines if l["kind"] == "command"]
    last_map, last_battle, last_gtext = object(), None, None
    ok = bad = 0
    total_dur = 0.0
    for l in lines:
        if l["kind"] == "command":
            r = l.get("result") or {}
            (ok, bad) = (ok + 1, bad) if r.get("ok") else (ok, bad + 1)
            total_dur += l.get("dur") or 0
        elif l["kind"] == "sample":
            st = l.get("state") or {}
            g = st.get("game") or {}
            m = g.get("map") or {}
            mid = m.get("id")
            if isinstance(mid, int) and 0 <= mid < 100000 and mid != last_map:
                maps.append((l["t"], mid, m.get("x"), m.get("z")))
                last_map = mid
            b = bool((st.get("screen") or {}).get("battle"))
            if last_battle is not None and b != last_battle:
                battles.append((l["t"], b))
            last_battle = b
            gt = (l.get("main_goal") or {}).get("text")
            if gt and gt != last_gtext:
                goal_changes.append((l["t"], goal_label(l.get("main_goal"))))
                last_gtext = gt

    meta = json.load(open(os.path.join(exp, "meta.json")))
    print(f"experiment:  {exp}")
    print(f"started:     {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(meta['started']))}")
    print(f"duration:    {hhmmss(lines[-1]['t'], t0) if lines else '0'} (of {meta['duration_s'] / 60:.0f} min)")
    print(f"trace kinds: {kinds}")
    print(f"commands:    {len(cmds)}  (ok: {ok}, failed: {bad}, busy-time: {total_dur:.0f}s)")
    print(f"\ngoal changes ({len(goal_changes)}):")
    for t, g in goal_changes[:20]:
        print(f"  {hhmmss(t, t0)}  {g}")
    print(f"\nmap visits ({len(maps)}):")
    for t, mid, x, z in maps[:20]:
        print(f"  {hhmmss(t, t0)}  map {mid} at ({x},{z})")
    if battles:
        print(f"\nbattle toggles: {len(battles)}")
        for t, b in battles[:10]:
            print(f"  {hhmmss(t, t0)}  {'started' if b else 'ended'}")
    last_sample = next((l for l in reversed(lines) if l["kind"] == "sample"), None)
    if last_sample:
        st = last_sample.get("state") or {}
        g = st.get("game") or {}
        m = g.get("map") or {}
        ctrl = (last_sample.get("system1") or {}).get("controller")
        print(f"\nfinal state:  frame {st.get('frame')}, map {m.get('id')} pos ({m.get('x')},{m.get('z')}), "
              f"controller {ctrl['name'] if ctrl else 'idle'}")


def cmd_commands(exp, n):
    lines = [l for l in load(exp) if l["kind"] == "command"]
    t0 = lines[0]["t"] if lines else 0
    print(f"{len(lines)} commands (showing last {n}):\n")
    for l in lines[-n:]:
        r = l.get("result") or {}
        i = l.get("input") or {}
        flag = "ok " if r.get("ok") else "ERR"
        extra = {k: v for k, v in i.items() if k not in ("action", "goal")}
        print(f"{hhmmss(l['t'], t0)}  [{flag}] {i.get('action'):<15} {json.dumps(extra, default=str)[:60]:<62}"
              f" {('goal=' + str(i.get('goal')))[:45] if i.get('goal') else ''}")
        if not r.get("ok"):
            print(f"{'':12}  └─ {json.dumps(r)[:100]}")


def cmd_timeline(exp, n):
    """Commands + goal changes + key state transitions, chronological."""
    events = []
    last_map = last_battle = last_dialog = last_ctrl = last_gtext = object()
    lines = load(exp)
    t0 = lines[0]["t"] if lines else 0
    for l in lines:
        t, kind = l["t"], l["kind"]
        if kind == "experiment_started":
            events.append((t, "—", "experiment started"))
        elif kind == "command":
            i, r = l.get("input") or {}, l.get("result") or {}
            flag = "ok" if r.get("ok") else "ERR"
            sub = f" → {i['goal']}" if i.get("goal") else ""
            events.append((t, flag, f"cmd {i.get('action')} {json.dumps({k: v for k, v in i.items() if k not in ('action', 'goal')}, default=str)}{sub}"))
        elif kind == "sample":
            st = l.get("state") or {}
            g = st.get("game") or {}
            m = g.get("map") or {}
            mid = m.get("id")
            if isinstance(mid, int) and mid != last_map:
                events.append((t, "MAP", f"map {mid} at ({m.get('x')},{m.get('z')})"))
                last_map = mid
            b = bool((st.get("screen") or {}).get("battle"))
            if b != last_battle:
                events.append((t, "BAT" if b else "BAT", f"battle {'STARTED' if b else 'ended'}"))
                last_battle = b
            dlg = g.get("dialog")
            if dlg and dlg != last_dialog:
                events.append((t, "TXT", f"“{dlg[:60]}”"))
                last_dialog = dlg
            ctrl = (l.get("system1") or {}).get("controller")
            name = ctrl["name"] if ctrl else None
            if name != last_ctrl:
                events.append((t, "S1", f"controller {'→ ' + name if name else 'idle'}"))
                last_ctrl = name
            gt = (l.get("main_goal") or {}).get("text")
            if gt and gt != last_gtext:
                events.append((t, "GOAL", goal_label(l.get("main_goal"))))
                last_gtext = gt
    t0 = (lines[0]["t"] if lines else 0)
    print(f"timeline ({len(events)} events, last {n}):\n")
    for t, tag, msg in events[-n:]:
        print(f"{hhmmss(t, t0)}  {tag:<5} {msg}")


def cmd_path(exp, n=None):
    """tiles visited per map, from samples (dedup)."""
    tiles = {}
    for l in load(exp):
        if l["kind"] != "sample":
            continue
        m = ((l.get("state") or {}).get("game") or {}).get("map") or {}
        mid, x, z = m.get("id"), m.get("x"), m.get("z")
        if isinstance(mid, int) and 0 <= mid < 100000 and x is not None:
            tiles.setdefault(str(mid), set()).add((x, z))
    if not tiles:
        print("no field samples")
        return
    for mid, ts in sorted(tiles.items()):
        xs = [x for x, _ in ts]; zs = [z for _, z in ts]
        x0, x1, z0, z1 = min(xs), max(xs), min(zs), max(zs)
        print(f"map {mid}: {len(ts)} tiles  (x {x0}..{x1}, z {z0}..{z1})")
        for z in range(z0, z1 + 1):
            print("   " + "".join("●" if (x, z) in ts else "·" for x in range(x0, x1 + 1)))
        print()


# ---------------------------------------------------------------- html report
def cmd_report(exp, n=None):
    lines = load(exp)
    t0 = lines[0]["t"] if lines else 0
    meta = json.load(open(os.path.join(exp, "meta.json")))

    rows, last = [], {}
    for l in lines:
        t = hhmmss(l["t"], t0)
        kind = l["kind"]
        if kind == "command":
            i, r = l.get("input") or {}, l.get("result") or {}
            cls = "ok" if r.get("ok") else "err"
            rows.append((t, "cmd", cls,
                         f"{i.get('action')} {json.dumps({k: v for k, v in i.items() if k != 'action'}, default=str)}"
                         + (f" → result: {json.dumps(r, default=str)}" if r else "")))
        elif kind == "sample":
            st = l.get("state") or {}
            g = st.get("game") or {}
            m = g.get("map") or {}
            mid = m.get("id")
            if mid != last.get("map"):
                rows.append((t, "map", "map", f"entered map {mid} at ({m.get('x')},{m.get('z')})"))
                last["map"] = mid
            b = bool((st.get("screen") or {}).get("battle"))
            if b != last.get("battle"):
                rows.append((t, "battle", "err" if b else "ok", f"battle {'STARTED' if b else 'ended'}"))
                last["battle"] = b
            dlg = g.get("dialog")
            if dlg and dlg != last.get("dlg"):
                rows.append((t, "text", "txt", f"“{dlg}”"))
                last["dlg"] = dlg
            gt = (l.get("main_goal") or {}).get("text")
            gl = goal_label(l.get("main_goal"))
            if gt and gt != last.get("goal"):
                rows.append((t, "goal", "goal", gl))
                last["goal"] = gt
    shots = sorted(glob.glob(os.path.join(exp, "shots", "*.png")))
    out = os.path.join(exp, "report.html")
    with open(out, "w") as f:
        f.write(f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>trace {os.path.basename(exp)}</title>
<style>
body{{background:#0b0e14;color:#d7dce6;font-family:ui-monospace,Menlo,monospace;font-size:12px;margin:20px}}
h1{{color:#58c4dd;font-size:16px}} h2{{color:#7d8593;font-size:11px;letter-spacing:1.5px;text-transform:uppercase;margin-top:28px}}
table{{border-collapse:collapse;width:100%}} td{{padding:3px 8px;border-bottom:1px solid #232a3a;vertical-align:top}}
td.t{{color:#7d8593;white-space:nowrap}} .ok{{color:#3fd08c}} .err{{color:#ef6b73}} .map{{color:#58c4dd}}
.goal{{color:#b18cf0}} .txt{{color:#e6b450}} .shots img{{width:192px;margin:4px;border:1px solid #232a3a;border-radius:4px}}
.meta{{color:#7d8593}}
</style></head><body>
<h1>jev experiment · {os.path.basename(exp)}</h1>
<p class="meta">started {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(meta['started']))} ·
planned {meta['duration_s'] / 60:.0f} min · {len(rows)} notable events · {len(shots)} screenshots</p>
<h2>timeline</h2><table>{''.join(f'<tr><td class="t">{t}</td><td class="{c}">{k}</td><td>{e}</td></tr>' for t, k, c, e in rows)}</table>
<h2>screenshots</h2><div class="shots">{''.join(f'<img src="shots/{os.path.basename(p)}" title="{os.path.basename(p)}">' for p in shots)}</div>
</body></html>""")
    print(f"report written: {out}")


def cmd_close(exp):
    """Write summary.json for an experiment that was killed before finish()."""
    out = os.path.join(exp, "summary.json")
    if os.path.exists(out):
        print(f"already closed: {out}")
        return
    lines = load(exp)
    meta = json.load(open(os.path.join(exp, "meta.json")))
    counts, main_goal = {}, None
    for l in lines:
        counts[l["kind"]] = counts.get(l["kind"], 0) + 1
        g = l.get("main_goal")
        if g and g.get("main"):
            main_goal = g
    finished = lines[-1]["t"] if lines else meta["started"]
    summary = {
        "dir": exp, "started": meta["started"], "finished": finished,
        "elapsed_s": round(finished - meta["started"], 1),
        "counts": counts, "closed_post_hoc": True,
        "main_goal": main_goal,
        "actions_total": counts.get("command", 0),
    }
    json.dump(summary, open(out, "w"), indent=1)
    print(f"closed: {out}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["list", "summary", "timeline", "commands", "path", "report", "close"])
    ap.add_argument("exp", nargs="?", help="experiment dir (default: latest)")
    ap.add_argument("-n", type=int, default=40, help="how many lines to show")
    a = ap.parse_args()

    if a.cmd == "list":
        for d in sorted(glob.glob("experiments/exp_*")):
            done = os.path.exists(os.path.join(d, "summary.json"))
            n = sum(1 for _ in open(os.path.join(d, "trace.jsonl")))
            print(f"{d}  {'[closed]' if done else '[recording]'}  {n} lines")
        return
    if a.cmd == "close":
        cmd_close(resolve(a.exp))
        return
    exp = resolve(a.exp)
    if a.cmd == "summary":
        cmd_summary(exp)
        return
    {"timeline": cmd_timeline, "commands": cmd_commands,
     "path": cmd_path, "report": cmd_report}[a.cmd](exp, a.n)


if __name__ == "__main__":
    main()
