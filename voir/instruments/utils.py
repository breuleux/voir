"""Utilities for instruments."""

import time
from threading import Thread


class Monitor(Thread):
    """Thread that calls a monitoring function every ``delay`` seconds."""

    def __init__(self, delay, func):
        super().__init__(daemon=True)
        self.stopped = False
        self.delay = delay
        self.func = func

    def run(self):
        while not self.stopped:
            time.sleep(self.delay)
            self.func()

    def stop(self):
        self.stopped = True
