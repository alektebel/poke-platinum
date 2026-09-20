"""Experiment recorder: full JSONL trace of everything crossing the bridge.

One experiment = one directory:
  experiments/exp_<ts>/
    meta.json        run parameters
    trace.jsonl      append-only event log (commands, samples, events, goals)
    shots/           periodic gameplay screenshots

Thread-safe: the HTTP threads log commands, a sampler thread logs periodic
state/telemetry/event snapshots. After `duration` seconds the experiment is
closed with a summary.json.
"""
import io
import json
import os
import threading
import time


class Experiment:
    def __init__(self, app, telemetry, root="experiments", duration=0):
        ts = time.strftime("%Y%m%d_%H%M%S")
        self.dir = os.path.join(root, f"exp_{ts}")
        os.makedirs(os.path.join(self.dir, "shots"), exist_ok=True)
        self.app = app
        self.telemetry = telemetry
        self.duration = duration
        self.t0 = time.time()
        self.t_end = None
        self.counts = {}
        self.lock = threading.Lock()
        self._stop = threading.Event()
        self.trace_path = os.path.join(self.dir, "trace.jsonl")
        self.meta = {
            "started": self.t0, "rom": app.rom_path, "duration_s": duration,
            "pid": os.getpid(),
        }
        json.dump(self.meta, open(os.path.join(self.dir, "meta.json"), "w"), indent=1)
        self._trace = open(self.trace_path, "a", buffering=1)
        self.log("experiment_started", **self.meta)

    # -- writers ----------------------------------------------------------
    def log(self, kind, **kw):
        line = {"t": time.time(), "kind": kind, **kw}
        with self.lock:
            self._trace.write(json.dumps(line) + "\n")
            self.counts[kind] = self.counts.get(kind, 0) + 1

    def record_command(self, body, result, dur):
        self.log("command", input=body, result=result, dur=round(dur, 3))

    def info(self):
        return {"dir": self.dir, "recording": self.t_end is None,
                "elapsed_s": round((self.t_end or time.time()) - self.t0, 1),
                "counts": dict(self.counts)}

    # -- sampler ----------------------------------------------------------
    def _shot(self, n):
        png, _ = self.app.last_png()
        if png is None:
            return
        path = os.path.join(self.dir, "shots", f"{n:05d}.png")
        png.save(path)

    def run(self):
        last_seq = -1
        n = 0
        expired = False
        while not self._stop.is_set():
            if self.duration and time.time() - self.t0 >= self.duration:
                expired = True
                break
            try:
                raw = self.app.sensor.raw_state()
                tel = self.telemetry.snapshot(self.app)
                mem = getattr(self.app, "memory", None)
                events = []
                if mem is not None:
                    events = mem.events_since(last_seq)
                    if events:
                        last_seq = events[-1]["seq"]
                self.log("sample", state=raw, system1=tel.get("system1"),
                         main_goal=tel.get("main_goal"),
                         goals=(tel.get("goals") or [])[:5], events=events)
                if n % 5 == 0:  # every ~10s
                    self._shot(n)
            except Exception as e:
                self.log("sampler_error", error=str(e))
            n += 1
            self._stop.wait(2.0)
        if expired:
            print(f"[jev] experiment duration reached: {self.dir}")
            self.finish()

    def start(self):
        threading.Thread(target=self.run, daemon=True).start()

    def finish(self):
        if self.t_end is not None:
            return self.info()
        self.t_end = time.time()
        self.log("experiment_finished", elapsed_s=round(self.t_end - self.t0, 1))
        with self.lock:
            self._trace.flush()
        summary = {
            "dir": self.dir, "started": self.t0, "finished": self.t_end,
            "elapsed_s": round(self.t_end - self.t0, 1),
            "frames": self.app.frame, "counts": self.counts,
            "main_goal": self.telemetry.main_goal,
            "goals_total": len(self.telemetry.goals),
            "actions_total": len(self.telemetry.actions),
        }
        json.dump(summary, open(os.path.join(self.dir, "summary.json"), "w"), indent=1)
        return summary
