import sys
import time
import inspect
from contextlib import ExitStack, contextmanager
from queue import Empty, Queue
from types import ModuleType, SimpleNamespace

from giving import give, given

from .utils import exec_node, split_script, simple_bridge, MISSING


DEFAULT_PRIORITY = 0


class StopProgram(Exception):
    """Raise to stop the benchmark."""


def as_instrument(x):
    if isinstance(x, str):
        rval = simple_bridge(x)
    elif inspect.isgeneratorfunction(x):
        rval = contextmanager(x)
    elif inspect.isfunction(x) or hasattr(x, "__enter__"):
        rval = x
    else:
        raise TypeError(
            "An instrument must be a string representing a probe,"
            " a function or a context manager."
        )
    if not hasattr(rval, "priority"):
        rval.priority = DEFAULT_PRIORITY
    return rval


class InstrumentState:
    def __init__(self, overseer, config):
        self.overseer = overseer
        if isinstance(config, dict):
            self.config = SimpleNamespace(**config)
        else:
            self.config = config
        self.state = SimpleNamespace()

        # Forward methods
        self.probe = overseer.probe
        self.require = overseer.require
        self.queue = overseer.queue
        self.given = overseer.given
        self.give = overseer.give


class Overseer:
    def __init__(self, *, fn, args, kwargs, instruments={}):
        self.fn = fn
        self.argv = sys.argv
        self.args = args
        self.kwargs = kwargs
        self.instruments = [
            (as_instrument(instrument), config)
            for instrument, config in instruments.items()
        ]
        self.instruments.sort(key=lambda pair: pair[0].priority)
        self.give = give
        self.given = None
        self._entered = False
        self._queue = Queue()

    def probe(self, *selectors):
        self.push_instrument(simple_bridge(*selectors))

    def require(self, instrument, argument=MISSING, **config):
        instrument = as_instrument(instrument)
        assert not (config and argument is not MISSING)
        if argument is not MISSING:
            config = argument
        state = InstrumentState(self, config)
        ctx = instrument(state)
        if hasattr(ctx, "__enter__"):
            self._stack.enter_context(ctx)
        return state

    def stop(self, message=None):
        """Stop the program."""
        raise StopProgram(message)

    def queue(self, **data):
        """Give data into a queue, typically from other threads."""
        data["#queued"] = time.time()
        self._queue.put(data)

    def run(self):
        """Run the program."""
        assert not self._entered
        self._entered = True
        try:
            with given() as gv:
                self.give = give
                self.given = gv

                @gv.where("!#queued").subscribe
                def _(_):
                    # Insert the queued data into the given() stream
                    # whenever other data comes in
                    while True:
                        try:
                            data = self._queue.get_nowait()
                            give(**data)
                        except Empty:
                            break

                self._stack = ExitStack()
                with self._stack:
                    for instrument, config in self.instruments:
                        self.require(instrument, config)

                    with give.wrap("run"):
                        self.fn(*self.args, **self.kwargs)

        except StopProgram:
            pass


def run_script(script, field, argv, instruments):
    node, mainsection = split_script(script)
    mod = ModuleType("__main__")
    glb = vars(mod)
    glb["__file__"] = script
    sys.modules["__main__"] = mod
    code = compile(node, script, "exec")
    exec(code, glb, glb)
    glb["__main__"] = exec_node(script, mainsection, glb)

    sys.argv = [script, *argv]

    ov = Overseer(
        fn=glb[field],
        args=(),
        kwargs={},
        instruments=instruments,
    )
    ov.run()
