import json
import os
import sys
import traceback
from argparse import REMAINDER
from types import ModuleType

import yaml
from giving import SourceProxy
from ptera import probing, select

from .argparse_ext import ExtendedArgumentParser
from .helpers import current_overseer
from .phase import GivenPhaseRunner
from .scriptutils import exec_node, split_script


class GiveToFile:
    def __init__(self, filename, fields=None, require_writable=True):
        self.fields = fields
        self.filename = filename
        try:
            self.out = open(self.filename, "w", buffering=1)
        except OSError:
            if require_writable:
                raise
            self.out = open(os.devnull, "w")
        self.out.__enter__()

    def log(self, data):
        try:
            txt = json.dumps(data)
        except TypeError:
            try:
                txt = json.dumps({"$unserializable": str(data)})
            except Exception:
                txt = json.dumps({"$unrepresentable": None})
        self.out.write(f"{txt}\n")

    def close(self):
        self.out.__exit__()


class LogStream(SourceProxy):
    def __call__(self, data):
        self._push(data)


class ProbeInstrument:
    def __init__(self, selector):
        self.selector = selector
        self.probe = self.__state__ = probing(self.selector)

    def __call__(self, ov):
        yield ov.phases.load_script(priority=0)
        with self.probe:
            yield ov.phases.run_script(priority=0)


class Overseer(GivenPhaseRunner):
    def __init__(self, instruments, logfile=None):
        self.argparser = ExtendedArgumentParser()
        self.argparser.add_argument("SCRIPT")
        self.argparser.add_argument("ARGV", nargs=REMAINDER)
        super().__init__(
            phase_names=["init", "parse_args", "load_script", "run_script", "finalize"],
            args=(self,),
            kwargs={},
        )
        for instrument in instruments:
            self.require(instrument)
        self.logfile = logfile

    def on_overseer_error(self, e):
        self.log(
            {
                "$event": "overseer_error",
                "$data": {"type": type(e).__name__, "message": str(e)},
            }
        )
        print("=" * 80, file=sys.stderr)
        print(
            "voir: An error occurred in an overseer. Execution proceeds as normal.",
            file=sys.stderr,
        )
        print("=" * 80, file=sys.stderr)
        traceback.print_exception(type(e), e, e.__traceback__)
        print("=" * 80, file=sys.stderr)
        super().on_overseer_error(e)

    def probe(self, selector):
        return self.require(ProbeInstrument(select(selector, skip_frames=1)))

    def run_phase(self, phase):
        self.log({"$event": "phase", "$data": {"name": phase.name}})
        return super().run_phase(phase)

    def run(self, argv):
        self.log = LogStream()
        self.given.where("$event") >> self.log
        if self.logfile is not None:
            self.gtf = GiveToFile(self.logfile, require_writable=False)
            self.log >> self.gtf.log
        else:
            self.gtf = None

        with self.run_phase(self.phases.init):
            tmp_argparser = ExtendedArgumentParser(add_help=False)
            tmp_argparser.add_argument("--config", action="append", default=[])
            tmp_options, argv = tmp_argparser.parse_known_args(argv)
            for config in tmp_options.config:
                self.argparser.merge_base_config(yaml.safe_load(open(config, "r")))

        with self.run_phase(self.phases.parse_args):
            self.options = self.argparser.parse_args(argv)
            del self.argparser

        with self.run_phase(self.phases.load_script):
            script = self.options.SCRIPT
            field = "__main__"
            argv = self.options.ARGV
            func = find_script(script, field)

        with self.run_phase(self.phases.run_script) as set_value:
            sys.argv = [script, *argv]
            set_value(func())

    def __call__(self, *args, **kwargs):
        token = current_overseer.set(self)
        try:
            super().__call__(*args, **kwargs)
        except BaseException as e:
            self.log(
                {
                    "$event": "error",
                    "$data": {"type": type(e).__name__, "message": str(e)},
                }
            )
            raise
        finally:
            with self.run_phase(self.phases.finalize):
                pass
            if self.gtf:
                self.gtf.close()
            current_overseer.reset(token)


def find_script(script, field):
    node, mainsection = split_script(script)
    mod = ModuleType("__main__")
    glb = vars(mod)
    glb["__file__"] = script
    sys.modules["__main__"] = mod
    code = compile(node, script, "exec")
    exec(code, glb, glb)
    glb["__main__"] = exec_node(script, mainsection, glb)
    return glb[field]
