"""This module defines the Overseer, the main interface that instruments can use.

All instruments receive an :class:`Overseer` as their first argument.
"""

import importlib
import json
import os
import pkgutil
import sys
import traceback
from argparse import REMAINDER, Namespace
from pathlib import Path
from typing import Union

import yaml
from giving import Given, SourceProxy
from ptera import Probe, probing, select

from voir.smuggle import SmuggleWriter

from .argparse_ext import ExtendedArgumentParser
from .helpers import current_overseer
from .phase import GivenOverseer, Phase, PhaseSequence
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
    """Callable wrapper over :class:`giving.gvn.SourceProxy`.

    This has the same interface as :class:`giving.gvn.Given`.
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

    def __init__(self, selector, **kwargs):
        self.selector = selector
        self.probe = self.__state__ = probing(self.selector, **kwargs)

    def __call__(self, ov):
        yield ov.phases.load_script(priority=0)
        with self.probe:
            yield ov.phases.run_script(priority=0)


class Overseer(GivenOverseer):
    """Oversee the running of a script and schedule instruments.

    When called with command-line arguments, the Overseer will parse instrument
    configuration, followed by the script to run (first positional argument), and
    then the script's arguments. Then it will load and run the script. Here is the
    sequence of phases. An instrument should yield a phase to wait until it is ended:

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

    phases: PhaseSequence
    """Sequence of phases the Overseer goes through."""

    log: LogStream
    """A stream of data to log to $DATA_FD, possibly to the dashboard."""

    given: Given
    """A stream of data created by calls to :func:`~giving.api.give`."""

    argparser: ExtendedArgumentParser
    """The argument parser for voir, given before the script."""

    options: Namespace
    """The parsed arguments."""

    logfile: Union[str, int]
    """The name of the file to log to, or an integer file descriptor."""

    def __init__(self, instruments, logfile=None):
        """Initialize an Overseer.

        Arguments:
            instruments: Collection of instruments to require.
            logfile: Filename to log to, or integer file descriptor.
        """
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
        self.require(*instruments)
        self.logfile = logfile

    def probe(self, selector: str, **kwargs) -> Probe:
        """Create a :class:`ProbeInstrument` on the given selector.

        >>> probe = overseer.probe("f > x")
        >>> probe.display()

        Arguments:
            selector: The selector to probe.
        """
        return self.require(ProbeInstrument(select(selector, skip_frames=1), **kwargs))

    def run_phase(self, phase: Phase):
        """Context manager to run a phase.

        >>> with self.run_phase(self.phases.peanuts):
        ...     do_stuff()

        The body of the with statement is run, and then all instruments that
        yielded that phase (in order to wait for its end) are resumed, in
        priority order.

        Arguments:
            phase: The phase to run.
        """
        self.log({"$event": "phase", "$data": {"name": phase.name}})
        return super().run_phase(phase)

    ####################
    # Internal methods #
    ####################

    def _on_instrument_error(self, e):
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
        super()._on_instrument_error(e)

    def _run(self, argv):
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

    def _prepare(self):
        super()._prepare()
        self._token = current_overseer.set(self)

    def _on_error(self, e):
        self.log(
            {
                "$event": "error",
                "$data": {"type": type(e).__name__, "message": str(e)},
            }
        )

    def _finish(self):
        super()._finish()
        with self.run_phase(self.phases.finalize):
            pass
        if self._logger:
            self._logger.close()
        current_overseer.reset(self._token)


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
