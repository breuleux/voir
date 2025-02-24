"""Phase and generator-based system to run plugins.

Overseer is based on functionality in this file.
"""

from __future__ import annotations

import heapq
import inspect
import threading
import time
from contextlib import contextmanager
from itertools import count
from queue import Empty, Queue

from giving import give, given

_gid = count()


class StopProgram(BaseException):
    """Raise from a handler/instrument to stop the program."""

    # Inherit from BaseException so that it isn't caught by "except Exception"
    # in user code. In that sense it is supposed to work a bit like
    # KeyboardInterrupt.


class OverseerAbort(BaseException):
    """Raise to abort the program."""


class Phase:
    """Phase of a process."""

    name: str
    """Name of the phase."""

    status: str
    """Phase status ("pending", "done" or "running")"""

    value: object
    """Result of the phase."""

    exception: BaseException
    """If the phase failed, contains the corresponding exception.

    If the phase succeeded, this is None."""

    def __init__(self, name, status="pending"):
        self.name = name
        self.status = status
        self.value = None
        self.exception = None

    @property
    def pending(self):
        """Return whether the phase is pending."""
        return self.status == "pending"

    @property
    def done(self):
        """Return whether the phase is done."""
        return self.status == "done"

    @property
    def running(self):
        """Return whether the phase is running."""
        return self.status == "running"

    def __call__(self, priority=0) -> PhaseWithPriority:
        """Attach a priority when waiting for this phase."""
        return PhaseWithPriority(phase=self, priority=priority)


class PhaseWithPriority:
    """Associate a phase to wait for to a priority."""

    phase: Phase
    """Phase to wait for."""

    priority: int
    """Priority after the phase is over (higher is run first)."""

    def __init__(self, phase, priority):
        self.phase = phase
        self.priority = priority


class PhaseSequence:
    """Sequence of phases, also works as a namespace."""

    def __init__(self, **phases):
        self._sequence = list(phases.values())
        self.__dict__.update(phases)
        self._current = 0

    def __iter__(self):
        return iter(self._sequence)


class BaseOverseer:
    """Organizes and runs phases.

    Arguments:
        phase_names: The names of the phases. The Phase objects are created
            automatically.
        args: Positional arguments to give to each handler.
        kwargs: Keyword arguments to give to each handler.
    """

    def __init__(self, phase_names, args=(), kwargs={}):
        phases = {phase_name: Phase(phase_name) for phase_name in phase_names}
        self.phases = PhaseSequence(_boot=Phase("_boot", status="done"), **phases)
        self.phases.IMMEDIATE = self.phases._boot(priority=0)
        self.handlers = set()
        # The plan maps each phase to a heap queue. The heap queue contains
        # (-priority, gid, generator, requested_phase) tuples, where gid is a
        # monotonically increasing number used to ensure that we follow
        # require() order when priorities are equal. The requested_phase is what
        # the generator last yielded and determines what is sent or thrown to
        # it.
        self.plan = {phase: [] for phase in self.phases}
        self.handler_args = args
        self.handler_kwargs = kwargs
        self.status = "init"
        self._to_require = []

    def _require(self, func):
        """Add a new handler.

        The same ``func`` will only be added once.

        The callable will be called with ``self.handler_args`` and
        ``self.handler_kwargs``. If it returns a generator, the generator must
        yield phases from ``self.phases``. The generator is immediately executed
        for all phases that are already done, and then queued for the next phase
        that is either currently processed or to be processed in the future.

        Any errors in the handler are passed to ``self._on_instrument_error``.

        Arguments:
            func: A callable.
        """
        state = getattr(func, "__state__", func)

        if self.status == "init":
            self._to_require.append(func)
            return state

        if func in self.handlers:
            return state

        self.handlers.add(func)

        try:
            gen = func(*self.handler_args, **self.handler_kwargs)
        except StopProgram as stp:
            self._on_stop(*stp.args)
            raise
        except BaseException as exc:
            self._on_instrument_error(exc)
            return

        if not inspect.isgenerator(gen):
            return state

        self._step((0, next(_gid), gen, self.phases._boot))
        return state

    def require(self, *instruments):
        """Register instruments.

        Each instrument should be a callable or generator function that takes the
        overseer ``ov`` as its first argument. If it returns a generator, it must
        yield phases from ``ov.phases``. The generator is immediately executed
        for all phases that are already done, and then queued for the next phase
        that is either currently processed or to be processed in the future.

        Arguments:
            instruments: Callables or generator functions.
        """
        states = [self._require(instrument) for instrument in instruments]
        return states[0] if len(states) == 1 else states

    def stop(self, value: object = None):
        """Stop the program.

        This method is meant to be used to stop a program early because e.g. the
        instrument considers that it has run long enough or that enough data has
        been collected.

        A :class:`StopProgram` exception is propagated to each instrument, but it
        is not propagated to the top level.

        Arguments:
            value: A value to attach to the StopProgram exception.
        """
        raise StopProgram(value)

    def abort(self, exc: BaseException):
        """Stop the program by raising an error.

        Arguments:
            exc: The exception to raise.
        """
        raise OverseerAbort(exc)

    def _on_instrument_error(self, e):
        pass

    def _on_stop(self, value):
        self.status = "stopped"
        for entries in self.plan.values():
            for _, __, gen, ___ in entries:
                try:
                    gen.throw(StopProgram(value))
                except (StopProgram, StopIteration):
                    pass
                except BaseException as exc:
                    self._on_instrument_error(exc)

    def _step(self, entry):
        """Step for one generator.

        Arguments:
            entry: A (priority, gid, generator, requested_phase) tuple.
        """
        _, gid, gen, next_phase = entry
        while True:
            next_phase, next_priority = self._step_one(gen, next_phase)
            if next_phase is None:
                return
            elif not next_phase.done:
                break
        heapq.heappush(self.plan[next_phase], (-next_priority, gid, gen, next_phase))

    def _step_one(self, gen, ph):
        """Run one step of the generator using the given phase.

        The generator is sent ph.value, or thrown ph.exception, depending on
        whether ph.exception is None or not. Any errors are caught and sent
        to the error handler.
        """
        try:
            if ph.exception is not None:
                try:
                    next_phase = gen.throw(ph.exception)
                except BaseException as exc:
                    if exc is not ph.exception:
                        # Note: StopIteration will follow this path
                        raise
                    else:
                        return None, None
            else:
                next_phase = gen.send(ph.value)
            if isinstance(next_phase, PhaseWithPriority):
                next_priority = next_phase.priority
                next_phase = next_phase.phase
            else:
                next_priority = 0
            if next_phase not in self.phases:
                raise Exception("Generator must yield a valid phase")
        except StopIteration:
            return None, None
        except StopProgram:
            raise
        except OverseerAbort as exc:
            raise exc
        except BaseException as exc:
            self._on_instrument_error(exc)
            return None, None
        return next_phase, next_priority

    @contextmanager
    def run_phase(self, phase: Phase):
        """Run a phase.

        Arguments:
            phase: One of the Phases in ``self.phases``.
        """
        result = exception = None

        def _set_value(value):
            nonlocal result
            result = value

        try:
            yield _set_value
        except BaseException as exc:
            exception = exc

        phase.status = "running"
        phase.value = result
        phase.exception = exception
        entries = self.plan[phase]

        try:
            while entries:
                # Note: existing coroutines can call require() to add new entries,
                # so the heap can become larger from an iteration to the next.
                entry = heapq.heappop(entries)
                self._step(entry)
            phase.status = "done"
        except OverseerAbort as exc:
            raise exc.args[0]
        else:
            if exception:
                raise exception

    def _prepare(self):
        if self.status != "init":
            raise Exception("Can only enter runner when status == 'init'")
        self.status = "running"
        for req in self._to_require:
            self.require(req)

    def _run(self, *args, **kwargs):
        pass

    def _on_error(self, exc):
        pass

    def _finish(self):
        pass

    def __call__(self, *args, **kwargs):
        """Execute the program through the overseer."""
        try:
            self._prepare()
            self._run(*args, **kwargs)
        except StopProgram as stp:
            self._on_stop(*stp.args)
        except BaseException as e:
            self._on_error(e)
            raise
        finally:
            self._finish()


class GivenOverseer(BaseOverseer):
    """Phase runner that provides an interface to giving.give."""

    def __init__(self, phase_names, args=(), kwargs={}):
        super().__init__(
            phase_names=phase_names,
            args=args,
            kwargs=kwargs,
        )
        self._queue = Queue()
        self._thread = threading.current_thread()
        self._queue_called = False

    def give(self, **data):
        """Push data into the self.given stream.

        This works properly when called from different threads than the main one,
        by calling ``self.queue`` in that case.
        """
        if threading.current_thread() is self._thread:
            give(**data)
        else:
            self.queue(**data)

    def _dump_queue(self):
        if self._queue_called:
            while True:
                try:
                    data = self._queue.get_nowait()
                    give(**data)
                except Empty:
                    break

    def queue(self, **data):
        """Give data into a queue, typically from other threads."""
        if not self._queue_called:
            qd = self.given.where("!$queued")

            @qd.subscribe
            def _(_):
                # Insert the queued data into the given() stream
                # whenever other data comes in
                self._dump_queue()

        self._queue_called = True

        data["$queued"] = time.time()
        self._queue.put(data)

    def _prepare(self):
        super()._prepare()
        self.given = given().__enter__()

    def _finish(self):
        self._dump_queue()
        self.given.__exit__(None, None, None)
        super()._finish()
