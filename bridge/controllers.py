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
    name = "walk_to"

    def __init__(self, x, y, body):
        super().__init__(body)
        self.target = (x, y)

    def step(self, app):
        return True


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
    name = "battle_choice"

    def __init__(self, body):
        super().__init__(body)
        self.kind = body.get("kind", "move")
        self.index = max(0, min(int(body.get("index", 0)), 3))

    def step(self, app):
        return True
