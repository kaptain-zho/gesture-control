class GestureGate:
    """A deliberate hold, followed by neutral release, produces one event."""
    def __init__(self, hold=0.6, release=0.4, threshold=0.7):
        self.hold, self.release, self.threshold = hold, release, threshold
        self.reset()

    def reset(self):
        self.candidate = None
        self.since = None
        self.latched = False
        self.neutral_since = None
        self.progress = 0.0
        self.last_time = None
        self.held = 0.0
        self.uncertain_since = None
        self.previous_valid = False

    def update(self, gesture, confidence, now):
        delta = 0 if self.last_time is None else max(0, now - self.last_time)
        if delta > 0.3:
            self.candidate, self.since = None, None
            self.neutral_since = None
            self.held = 0
            self.uncertain_since = None
            self.previous_valid = False
            if not self.latched: self.progress = 0
        self.last_time = now
        valid = gesture is not None and confidence >= self.threshold
        if self.latched:
            if valid:
                self.neutral_since = None
            elif self.neutral_since is None:
                self.neutral_since = now
            elif now - self.neutral_since >= self.release:
                self.latched = False
                self.candidate, self.since = None, None
                self.progress, self.held = 0, 0
                self.previous_valid = False
            return None
        if not valid:
            if self.uncertain_since is None:
                self.uncertain_since = now
            if now - self.uncertain_since > 0.15:
                self.candidate, self.since, self.progress = None, None, 0
                self.held = 0
            self.previous_valid = False
            return None
        if self.uncertain_since is not None and now - self.uncertain_since > 0.15:
            self.candidate = None
        if gesture != self.candidate:
            self.candidate, self.since = gesture, now
            self.held = 0
        elif self.previous_valid:
            self.held += delta
        self.previous_valid = True
        self.uncertain_since = None
        self.progress = min(1, self.held / self.hold)
        if self.progress >= 1:
            self.latched = True
            self.neutral_since = None
            return gesture
        return None
