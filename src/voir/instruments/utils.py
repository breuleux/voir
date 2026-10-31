"""Utilities for instruments."""

import multiprocessing
import threading
import time
from threading import Thread

# Upper bound on how long stop() waits for an in-flight poll to return
STOP_TIMEOUT = 30


def _join(thread):
    # Join so the poll is not running native code (e.g. jax memory_stats) when the
    # interpreter finalizes: on Python < 3.14 the thread is then pthread_exit'ed
    # while in C++ and the process aborts with "FATAL: exception not rethrown"
    if thread.is_alive() and thread is not threading.current_thread():
        thread.join(STOP_TIMEOUT)


class Monitor(Thread):
    """Thread that calls a monitoring function every ``delay`` seconds."""

    def __init__(self, delay, func):
        super().__init__(daemon=True)
        self._stop_event = threading.Event()
        self.delay = delay
        self.func = func

    @property
    def stopped(self):
        return self._stop_event.is_set()

    def run(self):
        while not self._stop_event.wait(self.delay):
            self.func()

    def stop(self):
        self._stop_event.set()
        _join(self)


def _worker(state, queue, func, delay, init=None):
    if init is not None:
        init()

    while state["running"]:
        queue.put(func())
        time.sleep(delay)


class ProcessMonitor:
    """Thread monitor does not produce metrics on regular intervals,
    if the current process is used extensively, using the process monitor
    helps.
    """

    def __init__(self, delay, func, worker_init=None):
        self.manager = multiprocessing.Manager()
        self.state = self.manager.dict()
        self.state["running"] = True
        self.results = multiprocessing.Queue()
        self.process = multiprocessing.Process(
            target=_worker,
            args=(self.state, self.results, func, delay, worker_init),
        )

    def start(self):
        self.process.start()

    def stop(self):
        self.state["running"] = False
        self.process.join()


class ProcessPusher(Thread):
    def __init__(self, delay, queue, func):
        super().__init__(daemon=True)
        self._stop_event = threading.Event()

        self.delay = delay
        self.queue = queue
        self.func = func

    def push(self):
        while not self.queue.empty():
            self.func(self.queue.get())

    @property
    def stopped(self):
        return self._stop_event.is_set()

    def run(self):
        while not self._stop_event.wait(self.delay):
            self.push()

    def stop(self):
        self._stop_event.set()
        _join(self)
        self.push()


class _Monitor:
    def __init__(self, *args):
        self.args = args

    def start(self):
        for a in self.args:
            a.start()

    def stop(self):
        for a in self.args:
            a.stop()


def monitor(delay, getfun, pushfun, process=True, worker_init=None):
    """Run the monitor in a different process to have metrics in regular intervals
    Pusher is a thread that gets executed when there is time.

    delay: float
        sleep time between observation

    getfun: () -> dict
        function used to retrieve metrics about the system

    pushfun: (dict) -> None
        function used on the main process once matrics are received.
        It can be used to save/display the data

    process: bool
        If true it will instantiate a new process for the monitoring
    """
    if process:
        m = []

        # Note: monitor needs to be first, so it stops generating observation first
        monitor = ProcessMonitor(delay, getfun, worker_init)
        m.append(monitor)
        m.append(ProcessPusher(delay, monitor.results, pushfun))
        return _Monitor(*m)
    else:
        if worker_init:
            worker_init()

    def fun():
        pushfun(getfun())

    monitor = Monitor(delay, fun)
    return monitor
