# jev-platinum

AI-agent bridge for Pokémon Platinum (NDS, US Rev 0). A localhost HTTP bridge wraps the
DeSmuME emulator (via `py-desmume`), exposing game state and validated actions so an LLM
"System 2" brain can set goals while deterministic controllers ("System 1") execute
frame-level input.

Mirrors the architecture of `jev-mindustry`: Sensor → `/state`, Actuator → `/command`.

## Layout

- `bridge/emu.py` — DeSmuME wrapper: frame loop, keypad/touch injection, savestates, window
- `bridge/server.py` — HTTP bridge (`/state`, `/catalog`, `/ping`, `/screen`, `/command`,
  `/events`, `/memory`, `/telemetry`) + live dashboard at `/`
- `bridge/actuator.py` — validated action execution on the emu thread
- `bridge/sensor.py` — RAM → JSON snapshot (calibration in progress)
- `bridge/controllers.py` — System 1: dialog/menu/battle/walk controllers
- `bridge/telemetry.py` — session telemetry: System 2 goals, jev's actions, live System 1 state
- `bridge/experiment.py` — experiment recorder: JSONL trace of everything crossing the bridge
- `bridge/web/index.html` — realtime dashboard (no build step, plain HTML/JS)
- `tools/` — driving/calibration scripts used to play through the intro
- `tools/trace.py` — inspect experiment traces (`list`, `summary`, `timeline`,
  `commands`, `path`, `report`, `close`)
- `experiments/exp_<ts>/` — recorded runs: `trace.jsonl`, `shots/`, `meta.json`,
  `summary.json`

## Run

```bash
pip install py-desmume py7zr pillow
python3 run_bridge.py                # windowed, port 7790
python3 tools/play.py state          # inspect game state
python3 tools/play.py shot out.png   # save a frame
```

Then open **http://127.0.0.1:7790/** in a browser for the live dashboard:

- left: DS screens (streamed), game state chips, dialog text, event stream
- right: System 2 main goal (+ goal history), live System 1 controller
  (phase/progress bar), and the action log — every `/command` jev executed,
  with its full input/result behind a "see more" expander

System 2 declares the main goal with either:

```json
{"action": "set_goal", "text": "Get the starter from Rowan"}
{"action": "walk_to", "x": 3, "z": 5, "goal": "walk to the stairs"}
```

## Status

- Bridge, input injection, touch, savestates, screenshots: working
- Sensor RAM map: wired and verified against live gameplay
  - `sFieldSystem` static (0x021BF680) → FieldSystem → Location / PlayerAvatar / MapObject
  - `/state` returns scene, map id, player grid x/z/facing, gender
  - Party block in the SaveData body: located at starter acquisition (TODO)
- Intro automation: title → Rowan script → bedroom driven by `tools/driver.py`
  (note: intro touch boxes need ≥10-frame key holds; bottom screen starts at
  composite row 196 of 388)
- Savestates: `rom/states/bedroom.ds0` = post-intro bedroom, control returned
- System 2 harness (`tools/brain.py`) + System 1 controllers: drives the map
  autonomously (frontier BFS over visited tiles, learned walls are *edges*,
  failed walk targets are memoized; WalkController aborts early on
  blocked/unreachable instead of burning its frame budget, and only aligned
  bumps count as wall evidence)

## Sensor map (calibrated)

```
sFieldSystem (0x021BF680) -> FieldSystem*
FS+0x0C SaveData*   FS+0x1C Location*   FS+0x38 MapObjectManager*   FS+0x3C PlayerAvatar*
Location:    mapHeaderID@0  warpId@4  x@8  z@0xC  facing@0x10
PlayerAvatar: gender@0x20   MapObject*@0x30
MapObject:   facingDir@0x28  x@0x64  y@0x68  z@0x6C  pos.fx32@0x70
sSaveDataPtr (0x021C0794) -> SaveData*  (body @+0x14; party page TBD)
```
