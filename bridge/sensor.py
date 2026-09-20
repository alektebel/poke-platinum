"""Stub snapshot. Real RAM map lands in the sensor phase (pokeplatinum symbols)."""
import time


class Sensor:
    def __init__(self, app):
        self.app = app
        self.t0 = time.time()

    def snapshot(self):
        app = self.app
        png, png_frame = app.last_png()
        return {
            "frame": app.frame,
            "fps": round(app.fps(), 1),
            "turbo": app.turbo,
            "keypad": app.keypad,
            "controller": app.controller.name if app.controller else None,
            "game": None,
            "note": "sensor_stub: RAM map not wired yet",
        }
