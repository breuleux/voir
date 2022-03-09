"""Phase and generator-based system to run plugins."""

import heapq
import inspect
from itertools import count

_gid = count()


class Phase:
    """Phase of a process.

    Attributes:
        name: Name of the phase.
        status: Phase status ("pending", "done" or "running")
        running: Whether the phase is running or not.
        done: Whether the phase is done or not.
        value: Result of the phase.
        exception: If the phase failed, contains the corresponding
            exception. If the phase succeeded, this is None.
    """

    def __init__(self, name, status="pending"):
        self.name = name
        self.status = "pending"
        self.value = None
        self.exception = None

    @property
    def done(self):
        return self.status == "done"

    @property
    def running(self):
        return self.status == "running"

    def __call__(self, priority=0):
        return PhaseWithPriority(phase=self, priority=priority)


class PhaseWithPriority:
    """Associate a phase to wait for to a priority."""

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


class PhaseRunner:
    """Organizes and runs phases.

    Arguments:
        phase_names: The names of the phases. The Phase objects are created
            automatically, and the "start" phase is added at the beginning.
        args: Positional arguments to give to each handler.
        kwargs: Keyword arguments to give to each handler.
        error_handler: Called whenever a handler raises an exception.
    """

    def __init__(self, phase_names, args=(), kwargs={}, error_handler=None):
        phases = {phase_name: Phase(phase_name) for phase_name in phase_names}
        self.phases = PhaseSequence(start=Phase("start"), **phases)
        self.phases.start.status = "done"
        self.handlers = set()
        # The plan maps each phase to a heap queue. The heap queue contains
        # (-priority, gid, generator, requested_phase) tuples, where
        # gid is a monotonically increasing number used to ensure that
        # we follow add() order when priorities are equal. The requested_phase
        # is what the generator last yielded and determines what is sent or
        # thrown to it.
        self.plan = {phase: [] for phase in self.phases}
        self.results = {}
        self.args = args
        self.kwargs = kwargs
        self.error_handler = error_handler

    def add(self, func):
        """Add a new handler.

        The same ``func`` will only be added once.

        The callable will be called with ``self.args`` and ``self.kwargs``. If
        it returns a generator, the generator must yield phases from
        ``self.phases``. The generator is immediately executed for all phases
        that are already done, and then queued for the next phase that is either
        currently processed or to be processed in the future.

        Any errors in the handler are passed to ``self.error_handler``.

        Arguments:
            func: A callable.
        """
        if func in self.handlers:
            return

        self.handlers.add(func)

        try:
            gen = func(*self.args, **self.kwargs)
        except BaseException as exc:
            self.error_handler(exc)
            return

        if not inspect.isgenerator(gen):
            return

        self._step((0, next(_gid), gen, self.phases.start))

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
        except StopIteration as exc:
            return None, None
        except BaseException as exc:
            self.error_handler(exc)
            return None, None
        return next_phase, next_priority

    def run_phase(self, phase, value, exception):
        """Run a phase.

        Arguments:
            phase: One of the Phases in ``self.phases``.
            value: The value for the phase.
            exception: The exception corresponding to this phase, or
                None if there is no error.
        """
        phase.status = "running"
        phase.value = value
        phase.exception = exception
        entries = self.plan[phase]
        while entries:
            # Note: existing coroutines can call add() to add new entries,
            # so the heap can become larger from an iteration to the next.
            entry = heapq.heappop(entries)
            self._step(entry)
        phase.status = "done"
