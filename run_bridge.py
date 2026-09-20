#!/usr/bin/env python3
import argparse
import faulthandler
import signal
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
    ap.add_argument("--record", action="store_true", help="record a full experiment trace")
    ap.add_argument("--record-minutes", dest="record_minutes", type=float, default=0,
                    help="auto-close the experiment after N minutes (0 = until shutdown)")
    ap.add_argument("--record-dir", dest="record_dir", default="experiments")
    args = ap.parse_args()

    faulthandler.register(signal.SIGUSR1, file=sys.stderr)  # debug: kill -USR1 <pid>

    app = EmuApp(args.rom, windowed=not args.headless, savestate_path=args.load_state)
    state = server.BridgeState(app, CATALOG)
    if args.record:
        from bridge.experiment import Experiment
        state.experiment = Experiment(app, state.telemetry, root=args.record_dir,
                                      duration=args.record_minutes * 60)
        print(f"[jev] recording experiment -> {state.experiment.dir}")
    srv = server.start(state, args.port)
    print(f"[jev] bridge listening on http://127.0.0.1:{args.port}")
    if state.experiment:
        state.experiment.start()

    try:
        app.run()
    except KeyboardInterrupt:
        pass
    finally:
        if state.experiment:
            summary = state.experiment.finish()
            print(f"[jev] experiment closed: {summary}")
        srv.shutdown()
        sys.exit(0)


if __name__ == "__main__":
    main()
