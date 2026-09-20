import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from desmume.controls import add_key, keymask, rm_key
from desmume.emulator import DeSmuME

from bridge import actuator
from bridge.keys import KEY_NAMES
from bridge.memory import Memory
from bridge.sensor import Sensor


class Pending:
    __slots__ = ("body", "done", "result")

    def __init__(self, body):
        self.body = body
        self.done = threading.Event()
        self.result = None


class EmuApp:
    def __init__(self, rom_path, windowed=True, savestate_path=None):
        self.rom_path = rom_path
        self.windowed = windowed
        self.emu = DeSmuME()
        self.win = None
        self.frame = 0
        self.turbo = False
        self.stopped = False
        self.queue = []
        self.queue_lock = threading.Lock()
        self.keypad = 0
        self.memory = Memory(os.path.join(os.path.dirname(rom_path), "states", "memory.json"))
        self.sensor = Sensor(self)
        self.controller = None
        self._fps = 0.0
        self._last_png = None
        self._png_frame = -1
        self._png_lock = threading.Lock()
        self._t0 = time.monotonic()
        self._frames_at_t0 = 0
        self.pending_state = savestate_path  # loaded once the emu is live

    def boot(self):
        self.emu.open(self.rom_path)
        if self.windowed:
            self.win = self.emu.create_sdl_window(auto_pause=False, use_opengl_if_possible=False)

    def run(self):
        self.boot()
        try:
            while not self.stopped:
                if self.pending_state is not None and self.frame >= 30:
                    path, self.pending_state = self.pending_state, None
                    try:
                        self.loadstate(path)
                        print(f"[jev] savestate loaded: {path}")
                    except Exception as e:
                        print(f"[jev] savestate load failed: {e}")
                self.step()
        finally:
            self.shutdown()

    def stop(self):
        self.stopped = True

    def submit(self, body):
        p = Pending(body)
        with self.queue_lock:
            self.queue.append(p)
        return p

    def drain_queue(self):
        while True:
            with self.queue_lock:
                if not self.queue:
                    return
                p = self.queue.pop(0)
            try:
                p.result = actuator.execute(self, p.body)
            except Exception as e:
                p.result = {"ok": False, "reason": f"exception:{type(e).__name__}:{e}"}
            p.done.set()

    def step(self):
        if self.controller is not None:
            try:
                if self.controller.step(self):
                    self.controller = None
            except Exception:
                self.controller = None
                self.keypad = 0
                self.apply_keypad()

        self.drain_queue()
        self.emu.cycle()
        self.frame += 1

        if self.win is not None:
            if not self.turbo or self.frame % 6 == 0:
                self.win.process_input()
                self.win.draw()
        else:
            self.emu.skip_next_frame()

        if self.frame % 2 == 0:
            self.capture_frame()
        if self.frame % 60 == 0:
            now = time.monotonic()
            dt = now - self._t0
            if dt > 0:
                self._fps = (self.frame - self._frames_at_t0) / dt
            self._t0 = now
            self._frames_at_t0 = self.frame

    def apply_keypad(self):
        self.emu.input.keypad_update(self.keypad)

    def press(self, names, frames=2, post_frames=2):
        mask = self.keypad
        for n in names:
            mask = add_key(mask, keymask(KEY_NAMES[n.upper()]))
        self.keypad = mask
        self.apply_keypad()
        self.run_frames(frames)
        for n in names:
            mask = rm_key(mask, keymask(KEY_NAMES[n.upper()]))
        self.keypad = mask
        self.apply_keypad()
        self.run_frames(post_frames)

    def hold(self, names):
        for n in names:
            self.keypad = add_key(self.keypad, keymask(KEY_NAMES[n.upper()]))
        self.apply_keypad()

    def release(self, names):
        for n in names:
            self.keypad = rm_key(self.keypad, keymask(KEY_NAMES[n.upper()]))
        self.apply_keypad()

    def release_all(self):
        self.keypad = 0
        self.apply_keypad()
        self.emu.input.touch_release()

    def touch(self, x, y):
        self.emu.input.touch_set_pos(x, y)

    def touch_release(self):
        self.emu.input.touch_release()

    def run_frames(self, n):
        for _ in range(min(n, 3600)):
            if self.stopped:
                return
            self.drain_queue()
            self.emu.cycle()
            self.frame += 1
            if self.win is not None:
                if not self.turbo or self.frame % 6 == 0:
                    self.win.process_input()
                    self.win.draw()
            if self.frame % 2 == 0:
                self.capture_frame()

    def capture_frame(self):
        with self._png_lock:
            try:
                self._last_png = self.emu.screenshot()
                self._png_frame = self.frame
            except Exception:
                pass

    def last_png(self):
        with self._png_lock:
            return self._last_png, self._png_frame

    def savestate(self, path):
        self.emu.savestate.save_file(path)

    def loadstate(self, path):
        self.emu.savestate.load_file(path)
        self.release_all()
        self.controller = None

    def fps(self):
        return self._fps

    def shutdown(self):
        self.release_all()
        if self.win is not None:
            try:
                self.win.destroy()
            except Exception:
                pass
