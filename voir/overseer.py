import importlib
import json
import os
import pkgutil
import sys
import traceback
from argparse import REMAINDER
from pathlib import Path

import yaml
from giving import SourceProxy
from ptera import probing, select

from voir.smuggle import SmuggleWriter

from .argparse_ext import ExtendedArgumentParser
from .helpers import current_overseer
from .phase import GivenPhaseRunner
from .scriptutils import resolve_script


class JsonlFileLogger:
    """Log data to a file as JSON lines.

    Arguments:
        filename: Either an integer representing a file descriptor to write to,
            or a path.
        require_writable: Require the file descriptor to be writable. If this is
            False and the file is not writable, this logger will simply forward
            the data to /dev/null instead of raising an OSError.
    """

    def __init__(self, filename, require_writable=True):
        self.filename = filename
        if self.filename == 1:
            self.out = SmuggleWriter(sys.stdout)
        elif self.filename == 2:
            self.out = SmuggleWriter(sys.stderr)
        else:
            try:
                self.out = open(self.filename, "w", buffering=1)
            except OSError:
                if require_writable:
                    raise
                self.out = open(os.devnull, "w")
        self.out.__enter__()

    def log(self, data):
        """Log a data dictionary as one JSON line into the file or file descriptor.

        If the data is not serializable as JSON, it will be dumped as
        ``{"$unserializable": repr(data)}``, and if _that_ fails, it will be
        dumped as the singularly uninformative ``{"$unrepresentable": None}``.
        """
        try:
            txt = json.dumps(data)
        except TypeError:
            try:
                txt = json.dumps({"$unserializable": repr(data)})
            except Exception:
                txt = json.dumps({"$unrepresentable": None})
        self.out.write(f"{txt}\n")

    def close(self):
        """Close the file."""
        self.out.__exit__()


class LogStream(SourceProxy):
    """Callable wrapper over giving.gvn.SourceProxy.

    This has the same interface as https://giving.readthedocs.io/en/latest/ref-gvn.html#giving.gvn.Given
    """

    def __call__(self, data):
        self._push(data)


class ProbeInstrument:
    """Instrument that creates a ptera.Probe on the given selector.

    The method ``overseer.probe()`` is shorthand for requiring an instance
    of this class.

    >>> probe = overseer.require(ProbeInstrument("f > x"))
    >>> probe.display()
    """

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
        self.argparser.add_argument("SCRIPT", nargs="?", help="The script to run")
        self.argparser.add_argument(
            "ARGV", nargs=REMAINDER, help="Arguments to the script"
        )
        self.argparser.add_argument(
            "-m",
            dest="MODULE",
            nargs=REMAINDER,
            help="Module or module:function to run",
        )

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
        """Create a :class:`ProbeInstrument` on the given selector.

        >>> probe = overseer.probe("f > x")
        >>> probe.display()
        """
        return self.require(ProbeInstrument(select(selector, skip_frames=1)))

    def run_phase(self, phase):
        """Run a phase."""
        self.log({"$event": "phase", "$data": {"name": phase.name}})
        return super().run_phase(phase)

    def run(self, argv):
        """Run the Overseer given the command-line arguments.

        Here is the sequence of phases. Await a phase in an instrument to wait
        until it is ended:

        * self.phases.init
            * Set up the logger and self.given
            * Parse the --config argument
        * self.phases.parse_args
            * Parse the command-line arguments
        * self.phases.load_script
            * Load the script's imports and functions
        * self.phases.run_script
            * Run the script
        """
        self.log = LogStream()
        self.given.where("$event") >> self.log
        if self.logfile is not None:
            self._logger = JsonlFileLogger(self.logfile, require_writable=False)
            self.log >> self._logger.log
        else:
            self._logger = None

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
            script, argv, func = _resolve_function(self.options)

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
            if self._logger:
                self._logger.close()
            current_overseer.reset(token)


def _resolve_function(options):
    """Resolve a function to call given an argparse options object.

    The relevant fields are ``(SCRIPT or MODULE) and ARGV``.
    """
    if script := options.SCRIPT:
        return script, options.ARGV, resolve_script(script)
    elif module_args := options.MODULE:
        module_spec, *argv = module_args
        if ":" in module_spec:
            module_name, field = module_spec.split(":", 1)
            module = importlib.import_module(module_name)
            return module_spec, argv, getattr(module, field)
        else:
            module_name = module_spec
            script = Path(pkgutil.get_loader(module_name).get_filename())
            if script.name == "__init__.py":
                script = script.parent / "__main__.py"
                module_name = f"{module_name}.__main__"
            script = str(script)
            return script, argv, resolve_script(script, module_name=module_name)
    else:
        sys.exit("Either SCRIPT or -m MODULE must be given.")
