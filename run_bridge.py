#!/usr/bin/env python3
import argparse
import sys

from bridge import server
from bridge.catalog import CATALOG
from bridge.emu import EmuApp


def main():
    ap = argparse.ArgumentParser(description="jev-platinum bridge")
    ap.add_argument("--rom", default="rom/3541 - Pokemon Platinum Version (US)(XenoPhobia).nds")
    ap.add_argument("--port", type=int, default=7790)
    ap.add_argument("--headless", action="store_true", help="no SDL window (frames will be blank without Xvfb)")
    ap.add_argument("--load-state", dest="load_state", help="savestate file to load at boot")
    args = ap.parse_args()

    app = EmuApp(args.rom, windowed=not args.headless)
    state = server.BridgeState(app, CATALOG)
    srv = server.start(state, args.port)
    print(f"[jev] bridge listening on http://127.0.0.1:{args.port}")

    if args.load_state:
        def _load():
            app.loadstate(args.load_state)
        import threading
        threading.Thread(target=_load, daemon=True).start()

    try:
        app.run()
    except KeyboardInterrupt:
        pass
    finally:
        srv.shutdown()
        sys.exit(0)


if __name__ == "__main__":
    main()
