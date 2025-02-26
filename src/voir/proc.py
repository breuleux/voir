"""Program runner.

Exports :func:`run(argv, ...)<run>` which can be used to run a program and iterate
over its stdout, stderr and data.

Exports the :class:`Multiplexer` class which can run multiple programs in parallel
and yield a unified stream of their stdout, stderr and any data that they generate
through ``voir``.
"""

import json
import os
import select
import subprocess
import time
from dataclasses import dataclass
from typing import Callable

from voir.smuggle import Decoder, MultimodalFile


@dataclass
class _Stream:
    pipe: object
    info: dict
    deserializer: Callable = None


@dataclass
class LogEntry:
    """An entry yielded by iterating over a :class:`Multiplexer`."""

    event: str
    """Name of the event (e.g. 'start', 'line', 'data', etc)."""

    data: object
    """Data associated to the event."""

    pipe: str = None
    """Pipe on which the event was produced (e.g. 'stdout', 'stderr', 'data')."""

    def get(self, item, default):
        return getattr(self, item, default)

    def dict(self):
        """Convert this entry to a plain dictionary."""
        return dict(self.__dict__)

    def json(self):
        """Convert this entry to JSON."""
        return json.dumps(self.__dict__)


def run(argv, info, timeout=None, constructor=None, env=None, **options):
    """Run a program.

    The result is a :class:`Multiplexer` that can be iterated over in order to
    get events corresponding to the start and end of the program as well as its
    stdout/stderr and data generated via ``voir``.

    Arguments:
        argv: The list of arguments.
        info: A dictionary of extra information that will be embedded in the
            ``LogEntry`` objects that are generated. The class given as the ``constructor``
            parameter should be able to take this information as keyword arguments
            in its ``__init__`` function.
        timeout: Timeout to use when using ``select`` to block on the next input.
        constructor: The subtype of :class:`LogEntry` to build log entries with.
            By default it is just ``LogEntry``.
        env: Environment variables to set.
        options: Other options to pass to :meth:`Multiplexer.start`.

    Returns:
        A Multiplexer running that program.
    """
    mp = Multiplexer(timeout=timeout, constructor=constructor)
    mp.start(argv, info=info, env=env, **options)
    return mp


class Multiplexer:
    """Run multiple programs in parallel and yield a unified stream of events.

    Iterating over a Multiplexer generates a sequence of :class:`LogEntry`:

    * The first event has ``event == "start"``.
    * Each line on stdout produces ``event == "line" and pipe == "stdout"``
    * Data logged through Voir produces ``event == "data" and pipe == "data" and data == the_data``.
    * The last event has ``event == "end"``.

    Arguments:
        timeout: Timeout to use when using ``select`` to block on the next input.
        constructor: The subtype of :class:`LogEntry` to build log entries with.
            By default it is just ``LogEntry``.
    """

    def __init__(self, timeout=0, constructor=None):
        self.processes = {}
        self.blocking = timeout is None
        self.timeout = timeout
        self.constructor = constructor or LogEntry
        self.buffer = []

    def start(self, argv, info, env=None, use_stdout=False, buffered=True, **options):
        """Start a process from the given ``argv``.

        Arguments:
            argv: The list of arguments.
            info: A dictionary of extra information that will be embedded in the
                ``LogEntry`` objects that are generated. The class given as the ``constructor``
                parameter should be able to take this information as keyword arguments
                in its ``__init__`` function.
            env: Environment variables to set, or None to pass ``os.environ``.
            use_stdout: If the program we are running is ``voir`` (``argv[0] == "voir"``)
                and ``use_stdout == True``, the ``DATA_FD`` environment variable will be
                set to 1, which is stdout. This will cause ``voir`` to smuggle data into
                the stdout file descriptor, and the Multiplexer will decode it
                transparently. See :mod:`voir.smuggle`.
            buffered: use to disable python output buffering.
                This is used to make test deterministic as buffering can cut lines are different spots.

        Returns:
            The subprocess object.
        """
        env = os.environ if env is None else env
        r, w = None, None
        buffered = "1" if buffered else "0"

        if use_stdout:
            proc = subprocess.Popen(
                argv,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env={**env, "DATA_FD": "1", "PYTHONUNBUFFERED": buffered},
                **options,
            )
            os.set_blocking(proc.stdout.fileno(), False)
            os.set_blocking(proc.stderr.fileno(), False)

            dec = Decoder(proc.stdout)
            mout = MultimodalFile(dec, "out", name=proc.stdout.name)
            mdat = MultimodalFile(dec, "data", name=proc.stdout.name)

            streams = [
                _Stream(pipe=mout, info={"pipe": "stdout"}, deserializer=None),
                _Stream(pipe=proc.stderr, info={"pipe": "stderr"}, deserializer=None),
                _Stream(pipe=mdat, info={"pipe": "data"}, deserializer=json.loads),
            ]

        else:
            r, w = os.pipe()
            proc = subprocess.Popen(
                argv,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                pass_fds=[w],
                env={**env, "DATA_FD": str(w), "PYTHONUNBUFFERED": buffered},
                **options,
            )
            readdata = open(r, "r", buffering=1)
            os.set_blocking(proc.stdout.fileno(), False)
            os.set_blocking(proc.stderr.fileno(), False)
            os.set_blocking(r, False)

            streams = [
                _Stream(pipe=proc.stdout, info={"pipe": "stdout"}, deserializer=None),
                _Stream(pipe=proc.stderr, info={"pipe": "stderr"}, deserializer=None),
                _Stream(pipe=readdata, info={"pipe": "data"}, deserializer=json.loads),
            ]

        self.add_process(
            proc=proc,
            argv=argv,
            info=info,
            streams=streams,
            w=w,
        )

        self.buffer.append(
            self.constructor(
                event="start",
                data={
                    "command": argv,
                    "time": time.time(),
                },
                **info,
            )
        )
        return proc

    def add_process(self, *, proc, info, argv, streams, w):
        """Add a process to those managed by this Multiplexer."""
        self.processes[proc] = (streams, argv, info, w)

    def _process_line(self, line, s, pinfo):
        try:
            if isinstance(line, bytes):
                line = line.decode("utf8")
            if s.deserializer:
                try:
                    data = s.deserializer(line)
                    if "$event" in data:
                        yield self.constructor(
                            event=data.pop("$event"),
                            data=data.pop("$data", None),
                            **data,
                            **pinfo,
                            **s.info,
                        )
                    else:
                        yield self.constructor(
                            event="data",
                            data=data,
                            **pinfo,
                            **s.info,
                        )
                except Exception as e:
                    yield self.constructor(
                        event="format_error",
                        data={
                            "line": line,
                            "type": type(e).__name__,
                            "message": str(e),
                        },
                        **pinfo,
                        **s.info,
                    )
            else:
                yield self.constructor(event="line", data=line, **pinfo, **s.info)
        except UnicodeDecodeError:
            yield self.constructor(event="binary", data=line, **pinfo, **s.info)

    def __iter__(self):
        """Iterate over all the events produced by the Multiplexer's processes."""
        yield from self.buffer
        self.buffer.clear()

        polling_obj = select.poll()
        to_consult = {}
        to_pipes = {}
        for proc, (streams, _, info, _) in self.processes.items():
            for s in streams:
                polling_obj.register(s.pipe, select.POLLIN | select.POLLPRI)
                entries = to_consult.setdefault(s.pipe, [])
                entries.append((s, proc, info))

                pipes = to_pipes.setdefault(s.pipe.fileno(), [])
                pipes.append(s.pipe)

        def close_resources(streams, w):
            for stream in streams:
                stream.pipe.close()

            if w is not None:
                try:
                    os.close(w)
                except Exception:
                    pass

        while self.processes:
            still_alive = set()
            ready = polling_obj.poll(self.timeout)

            for fd, event in ready:
                pipes = to_pipes[fd]
                for r in pipes:
                    while line := r.readline():
                        for s, proc, info in to_consult[r]:
                            yield from self._process_line(line, s, info)
                            still_alive.add(proc)

            for proc, (streams, argv, info, w) in list(self.processes.items()):
                if proc not in still_alive:
                    ret = proc.poll()
                    if ret is not None:
                        close_resources(streams, w)
                        del self.processes[proc]
                        yield self.constructor(
                            event="end",
                            data={
                                "command": argv,
                                "time": time.time(),
                                "return_code": ret,
                            },
                            **info,
                        )

            if not self.blocking:  # pragma: no cover
                yield None

        del polling_obj
