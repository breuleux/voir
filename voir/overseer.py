import sys
import traceback
from argparse import REMAINDER, ArgumentParser
from types import ModuleType

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
        with self.run_phase(self.phases.init):
            pass

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
        try:
            super().__call__(*args, **kwargs)
        finally:
            with self.run_phase(self.phases.finalize):
                pass


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
