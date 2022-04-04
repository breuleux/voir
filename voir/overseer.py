import sys
import traceback
from argparse import REMAINDER, ArgumentParser
from types import ModuleType

from giving import given
from ptera import probing, select

from .phase import GivenPhaseRunner, StopProgram
from .utils import exec_node, split_script


class ProbeInstrument:
    def __init__(self, selector):
        self.selector = selector
        self.probe = self.__state__ = probing(self.selector)

    def __call__(self, ov):
        yield ov.phases.load_script(priority=0)
        with self.probe:
            yield ov.phases.run_script(priority=0)


class Overseer(GivenPhaseRunner):
    def __init__(self, instruments):
        self.suppress_error = False
        self.argparser = ArgumentParser()
        self.argparser.add_argument("SCRIPT")
        self.argparser.add_argument("ARGV", nargs=REMAINDER)
        super().__init__(
            phase_names=["init", "parse_args", "load_script", "run_script", "finalize"],
            args=(self,),
            kwargs={},
        )
        for instrument in instruments:
            self.require(instrument)

    def on_error(self, exc):
        if not self.suppress_error:
            print("An error occurred", file=sys.stderr)
            traceback.print_exception(type(exc), exc, exc.__traceback__)

    def probe(self, selector):
        return self.require(ProbeInstrument(select(selector, skip_frames=1)))

    def run(self, argv):
        self.run_phase(self.phases.init, None, None)
        self.options = self.argparser.parse_args(argv)
        del self.argparser
        self.run_phase(self.phases.parse_args, None, None)
        script = self.options.SCRIPT
        field = "__main__"
        argv = self.options.ARGV

        try:
            func = find_script(script, field)
        except BaseException as exc:
            self.run_phase(self.phases.load_script, None, exc)
            self.on_error(exc)
            return False

        self.run_phase(self.phases.load_script, None, None)
        sys.argv = [script, *argv]
        result, exception = None, None
        try:
            result = func()
        except BaseException as exc:
            exception = exc
        self.run_phase(self.phases.run_script, result, exception)
        if exception is not None and not isinstance(exception, StopProgram):
            if isinstance(exception, SystemExit):
                raise exception
            self.on_error(exception)
            return False

    def __call__(self, *args, **kwargs):
        try:
            super().__call__(*args, **kwargs)
        finally:
            self.run_phase(self.phases.finalize, None, None)


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
