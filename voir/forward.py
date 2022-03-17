import json
import os
import sys
import time
from contextlib import contextmanager, redirect_stderr, redirect_stdout

from giving import give

from .phase import StopProgram

REAL_STDOUT = sys.stdout


class FileGiver:
    def __init__(self, name, givefn=give):
        self.name = name
        self.givefn = givefn

    def write(self, x):
        self.givefn(**{self.name: x})

    def flush(self):  # pragma: no cover
        pass


@contextmanager
def give_std(givefn=give):
    with redirect_stdout(FileGiver("#stdout", givefn=givefn)):
        with redirect_stderr(FileGiver("#stderr", givefn=givefn)):
            yield


class JSONSerializer:
    def __init__(self, tags={}):
        self.tags = tags

    def gettag(self, label):
        return self.tags.get(label, label)

    def loads(self, s):
        try:
            data = json.loads(s)
            if not isinstance(data, dict):
                data = {self.gettag("#data"): data}
            return data
        except json.JSONDecodeError:
            return {self.gettag("#undeserializable"): s}

    def dumps(self, data):
        if not isinstance(data, dict):
            data = {self.gettag("#data"): data}
        try:
            return json.dumps(data)
        except TypeError:
            return json.dumps({self.gettag("#unserializable"): repr(data)})


class Forwarder:
    def __init__(self, write=None, serializer=None, fields=None):
        if write is None:  # pragma: no cover
            write = REAL_STDOUT.write
        self.write = write
        self.serializer = serializer or JSONSerializer()
        self.fields = fields

    def log(self, data):
        txt = self.serializer.dumps(data)
        self.write(f"{txt}\n")

    def __call__(self, ov):
        yield ov.phases.IMMEDIATE
        if self.fields:
            ov.given.keep(*self.fields) >> self.log
        else:
            ov.given >> self.log
        with give_std(ov.give):
            try:
                yield ov.phases.load_script
                yield ov.phases.run_script(priority=-1000)
            except StopProgram:  # pragma: no cover
                pass
            except BaseException as exc:
                ov.on_error(exc)
                ov.suppress_error = True
                raise


def _give(data):
    give(**data)


_serializer = JSONSerializer(
    tags={
        "#undeserializable": "#stdout",
        "#data": "#stdout",
    }
)


class MultiReader:
    def __init__(self, serializer=_serializer, handler=_give):
        self.processes = []
        self.serializer = serializer
        self.handler = handler

    def add_process(self, process, info):
        os.set_blocking(process.stdout.fileno(), False)
        self.processes.append((process, info))

    def __iter__(self):
        while self.processes:
            for (proc, info) in list(self.processes):
                while True:
                    line = proc.stdout.readline()
                    if not line:
                        ret = proc.poll()
                        if ret is not None:
                            # We do not read a line and the process is over
                            self.processes.remove((proc, info))
                            self.handler(
                                {"#end": time.time(), "#return_code": ret, **info}
                            )
                        break
                    try:
                        line = line.decode("utf8")
                        data = self.serializer.loads(line)
                    except UnicodeDecodeError:
                        data = {"#binout": line}
                    self.handler({**data, **info})
            yield
