class Controller:
    name = "base"

    def __init__(self, body):
        self.body = body
        self.ticks = 0

    def step(self, app):
        raise NotImplementedError


class DialogController(Controller):
    """Timed A-mash stopgap until dialog detection is live in the sensor."""
    name = "advance_dialog"

    def __init__(self, body):
        super().__init__(body)
        self.max_taps = min(int(body.get("max_taps", 60)), 300)
        self.taps = 0
        self.cooldown = 0

    def step(self, app):
        self.ticks += 1
        if self.cooldown > 0:
            self.cooldown -= 1
            return False
        if self.taps >= self.max_taps:
            return True
        app.press(["A"], frames=2, post_frames=8)
        self.taps += 1
        self.cooldown = 6
        return False


class WalkController(Controller):
    """Greedy tile-walker: step toward target, learn walls by bumping (#1+#5)."""
    name = "walk_to"

    DIRS = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}

    def __init__(self, x, z, body):
        super().__init__(body)
        self.target = (x, z)
        self.max_frames = min(int(body.get("max_frames", 7200)), 36000)
        self.hold_frames = max(int(body.get("hold_frames", 42)), 6)
        self.settle_frames = max(int(body.get("settle_frames", 18)), 4)
        self.phase = "idle"
        self.hold_dir = None
        self.origin = None
        self.phase_start = 0
        self.fail = 0
        self.visits = {}   # tiles entered this run; ping-pong = unreachable

    def step(self, app):
        self.ticks += 1
        if self.ticks > self.max_frames:
            app.release_all()
            return True
        st = app.sensor.field_state()
        if st is None:
            return False  # not in overworld (battle or scene load): wait
        map_id, x, z, facing = st

        scr = app.sensor.screen_state()
        if scr.get("message_box") or scr.get("yes_no"):
            app.release_all()
            self.phase = "idle"
            app.press(["A"], frames=3, post_frames=40)
            return False

        tx, tz = self.target
        dx, dz = tx - x, tz - z
        if dx == 0 and dz == 0:
            app.release_all()
            self.phase = "arrived"
            return True

        if self.phase == "idle":
            n = self.visits[(x, z)] = self.visits.get((x, z), 0) + 1
            if n > 3:
                # bouncing between the same tiles: target is not reachable
                # by walking (sealed or across water/ledges) — give up
                app.release_all()
                self.phase = "unreachable"
                return True
            mem = getattr(app, "memory", None)
            walls = set()
            if mem is not None and not self.body.get("ignore_walls"):
                m = mem.data["maps"].get(str(map_id), {})
                walls = {w.split(",")[2] for w in m.get("walls", [])
                         if w.startswith(f"{x},{z},")}
            # all four dirs, best-first by progress toward the target
            cands = sorted(self.DIRS, key=lambda d: -(dx * self.DIRS[d][0] + dz * self.DIRS[d][1]))
            dirs = [c for c in cands if c not in walls]
            if not dirs:
                # every step from here is a known wall: give up now instead
                # of bumping until max_frames
                app.release_all()
                self.phase = "blocked"
                return True
            self.hold_dir = dirs[0]
            self.origin = (x, z)
            self.phase = "hold"
            self.phase_start = self.ticks
            app.hold([self.hold_dir.upper()])
            return False
        if self.phase == "hold":
            if self.ticks - self.phase_start >= self.hold_frames:
                app.release_all()
                self.phase = "settle"
                self.phase_start = self.ticks
            return False
        # settle: verify movement, learn walls after repeated failures
        if self.ticks - self.phase_start >= self.settle_frames:
            mem = getattr(app, "memory", None)
            if (x, z) == self.origin:
                if facing == self.hold_dir:
                    # only aligned bumps are wall evidence: a player still
                    # turning (cornering) fails to move without a wall
                    self.fail += 1
                    if self.fail >= 2 and mem is not None:
                        mem.learn_wall(map_id, self.origin[0], self.origin[1], self.hold_dir)
            else:
                self.fail = 0
            self.phase = "idle"
        return False


class MenuController(Controller):
    name = "menu_navigate"

    def __init__(self, body):
        super().__init__(body)
        self.dir = body.get("dir", "down")
        self.count = int(body.get("count", 1))
        self.confirm = bool(body.get("confirm", False))
        self.done = 0
        self.cooldown = 0

    def step(self, app):
        if self.done >= self.count:
            if self.confirm:
                app.press(["A"], frames=2, post_frames=8)
            return True
        if self.cooldown > 0:
            self.cooldown -= 1
            return False
        key = {"up": "UP", "down": "DOWN", "left": "LEFT", "right": "RIGHT"}.get(self.dir)
        if key is None:
            return True
        app.press([key], frames=2, post_frames=6)
        self.done += 1
        self.cooldown = 4
        return False


class BattleController(Controller):
    """Screen-driven battle loop (#2+#3): FIGHT -> move 0, tracked by HP bars."""
    name = "battle_fight"

    def __init__(self, body):
        super().__init__(body)
        self.max_frames = min(int(body.get("max_frames", 14400)), 72000)
        self.move_index = max(0, min(int(body.get("index", 0)), 3))
        self.cooldown = 0
        self.taps = 0
        self.menu_seen = False

    def step(self, app):
        self.ticks += 1
        if self.ticks > self.max_frames:
            app.release_all()
            return True
        scr = app.sensor.screen_state()
        if not scr.get("battle"):
            # no HP bars: either pre/post battle text or battle over
            self.cooldown -= 1
            if self.cooldown < -600:   # ~10s with no battle UI: done
                return True
            if self.ticks % 30 == 0:
                app.press(["A"], frames=3, post_frames=25)
            return False
        self.cooldown = 200
        # battle UI visible: A-mash (FIGHT is the default cursor; move 0 next)
        if self.cooldown > 150:
            self.cooldown -= 1
            return False
        if self.ticks % 45 == 0:
            app.press(["A"], frames=3, post_frames=40)
            self.taps += 1
        return False
