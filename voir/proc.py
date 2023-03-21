import json
import os
import select
import subprocess
import time
from dataclasses import dataclass
from typing import Callable

from voir.smuggle import Decoder, MultimodalFile


@dataclass
class Stream:
    pipe: object
    info: dict
    deserializer: Callable = None


@dataclass
class LogEntry:
    event: str
    data: object
    pipe: str = None

    def get(self, item, default):
        return getattr(self, item, default)

    def dict(self):
        return dict(self.__dict__)

    def json(self):
        return json.dumps(self.__dict__)


def run(argv, info, timeout=None, constructor=None, env=os.environ, **options):
    mp = Multiplexer(timeout=timeout, constructor=constructor)
    mp.start(argv, info=info, env=env, **options)
    return mp


class Multiplexer:
    def __init__(self, timeout=0, constructor=None):
        self.processes = {}
        self.blocking = timeout is None
        self.timeout = timeout
        self.constructor = constructor or LogEntry
        self.buffer = []

    def start(self, argv, info, env=os.environ, use_stdout=False, **options):
        if use_stdout:
            proc = subprocess.Popen(
                argv,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env={**env, "DATA_FD": "1", "PYTHONUNBUFFERED": "1"},
                **options,
            )
            os.set_blocking(proc.stdout.fileno(), False)
            os.set_blocking(proc.stderr.fileno(), False)

            dec = Decoder(proc.stdout)
            mout = MultimodalFile(dec, "out", name=proc.stdout.name)
            mdat = MultimodalFile(dec, "data", name=proc.stdout.name)

            streams = [
                Stream(pipe=mout, info={"pipe": "stdout"}, deserializer=None),
                Stream(pipe=proc.stderr, info={"pipe": "stderr"}, deserializer=None),
                Stream(pipe=mdat, info={"pipe": "data"}, deserializer=json.loads),
            ]

        else:
            r, w = os.pipe()
            proc = subprocess.Popen(
                argv,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                pass_fds=[w],
                env={**env, "DATA_FD": str(w), "PYTHONUNBUFFERED": "1"},
                **options,
            )
            readdata = open(r, "r", buffering=1)
            os.set_blocking(proc.stdout.fileno(), False)
            os.set_blocking(proc.stderr.fileno(), False)
            os.set_blocking(r, False)

            streams = [
                Stream(pipe=proc.stdout, info={"pipe": "stdout"}, deserializer=None),
                Stream(pipe=proc.stderr, info={"pipe": "stderr"}, deserializer=None),
                Stream(pipe=readdata, info={"pipe": "data"}, deserializer=json.loads),
            ]

        self.add_process(
            proc=proc,
            argv=argv,
            info=info,
            streams=streams,
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

    def add_process(self, *, proc, info, argv, streams):
        self.processes[proc] = (streams, argv, info)

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
        yield from self.buffer
        self.buffer.clear()

        while self.processes:
            still_alive = set()
            to_consult = {}
            for proc, (streams, _, info) in self.processes.items():
                for s in streams:
                    entries = to_consult.setdefault(s.pipe, [])
                    entries.append((s, proc, info))

            ready, _, _ = select.select(to_consult.keys(), [], [], self.timeout)

            for r in ready:
                while line := r.readline():
                    for s, proc, info in to_consult[r]:
                        yield from self._process_line(line, s, info)
                        still_alive.add(proc)

            for proc, (streams, argv, info) in list(self.processes.items()):
                if proc not in still_alive:
                    ret = proc.poll()
                    if ret is not None:
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
