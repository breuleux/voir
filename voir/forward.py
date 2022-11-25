import json
import os
import select
import subprocess
import time
from dataclasses import dataclass
from typing import Callable


class GiveToFile:
    def __init__(self, filename, fields=None, require_existing=True):
        self.fields = fields
        self.filename = filename
        try:
            self.out = open(self.filename, "w", buffering=1)
        except OSError:
            if require_existing:
                raise
            self.out = open(os.devnull, "w")
        self.out.__enter__()
        self.serializer = json
        self.x = 0

    def log(self, data):
        try:
            txt = json.dumps(data)
        except TypeError:
            try:
                txt = json.dumps({"#unserializable": str(data)})
            except Exception:
                txt = json.dumps({"#unrepresentable": None})
        self.out.write(f"{txt}\n")

    def close(self):
        self.out.__exit__()


@dataclass
class Stream:
    pipe: object
    info: dict
    deserializer: Callable = None


class Multiplexer:
    def __init__(self, timeout=0):
        self.processes = {}
        self.blocking = timeout is None
        self.timeout = timeout
        self.buffer = []

    def run(self, argv, info, env=os.environ, **options):
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
        self.add_process(
            proc=proc,
            info=info,
            streams=[
                Stream(pipe=proc.stdout, info={"#pipe": "stdout"}, deserializer=None),
                Stream(pipe=proc.stderr, info={"#pipe": "stderr"}, deserializer=None),
                Stream(pipe=readdata, info={"#pipe": "data"}, deserializer=json.loads),
            ],
        )
        self.buffer.append(
            {
                "#event": "start",
                "#data": {
                    "time": time.time(),
                },
                **info,
            }
        )
        return proc

    def add_process(self, *, proc, info, streams):
        self.processes[proc] = (streams, info)

    def _process_line(self, line, s, pinfo):
        try:
            if isinstance(line, bytes):
                line = line.decode("utf8")
            if s.deserializer:
                try:
                    data = s.deserializer(line)
                    yield {"#event": "data", "#data": data, **pinfo, **s.info}
                except Exception as e:
                    yield {
                        "#event": "format_error",
                        "#data": {
                            "line": line,
                            "error": type(e).__name__,
                            "message": str(e),
                        },
                        **pinfo,
                        **s.info,
                    }
            else:
                yield {"#event": "line", "#data": line, **pinfo, **s.info}
        except UnicodeDecodeError:
            yield {"#event": "binary", "#data": line, **pinfo, **s.info}

    def __iter__(self):
        yield from self.buffer
        self.buffer.clear()

        while self.processes:
            still_alive = set()
            to_consult = {}
            for proc, (streams, info) in self.processes.items():
                to_consult.update({s.pipe: (s, proc, info) for s in streams})

            ready, _, _ = select.select(to_consult.keys(), [], [], self.timeout)

            for r in ready:
                while line := r.readline():
                    s, proc, info = to_consult[r]
                    yield from self._process_line(line, s, info)
                    still_alive.add(proc)

            for proc, (streams, info) in list(self.processes.items()):
                if proc not in still_alive:
                    ret = proc.poll()
                    if ret is not None:
                        del self.processes[proc]
                        yield (
                            {
                                "#event": "end",
                                "#data": {
                                    "time": time.time(),
                                    "return_code": ret,
                                },
                                **info,
                            }
                        )

            if not self.blocking:
                yield None
