# jev-platinum

AI-agent bridge for Pokémon Platinum (NDS, US Rev 0). A localhost HTTP bridge wraps the
DeSmuME emulator (via `py-desmume`), exposing game state and validated actions so an LLM
"System 2" brain can set goals while deterministic controllers ("System 1") execute
frame-level input.

Mirrors the architecture of `jev-mindustry`: Sensor → `/state`, Actuator → `/command`.

## Layout

- `bridge/emu.py` — DeSmuME wrapper: frame loop, keypad/touch injection, savestates, window
- `bridge/server.py` — HTTP bridge (`/state`, `/catalog`, `/ping`, `/screen`, `/command`)
- `bridge/actuator.py` — validated action execution on the emu thread
- `bridge/sensor.py` — RAM → JSON snapshot (calibration in progress)
- `bridge/controllers.py` — System 1: dialog/menu/battle/walk controllers
- `tools/` — driving/calibration scripts used to play through the intro

## Run

```bash
pip install py-desmume py7zr pillow
python3 run_bridge.py                # windowed, port 7790
python3 tools/play.py state          # inspect game state
python3 tools/play.py shot out.png   # save a frame
```

## Status

- Bridge, input injection, touch, savestates, screenshots: working
- Sensor RAM map: calibrating against live gameplay (gSystem / party / position)
