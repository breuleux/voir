"""This module defines tools to easily make configurable instruments."""

import functools
import inspect
from functools import partial

from ovld import meta, ovld


@ovld
def gated(flag: str):  # noqa: F811
    """Decorate an instrument so that it is only activated when a ``--flag`` is given.

    .. code-block:: python

        @gated("--xyz", "Ex why zee.")
        def instrument_xyz(ov):
            ...

    Arguments:
        flag: The name of the flag, e.g. ``"--flag"``
        help: Description of the flag.
        instrument: The instrument to place behind the flag.

    **List of signatures:**
    """
    return partial(gated, flag)


@ovld
def gated(flag: str, help: str):  # noqa: F811
    return partial(gated, flag, help=help)


@ovld
def gated(flag: str, instrument: meta(callable), help: str = None):  # noqa: F811
    dest = flag

    def run(ov):
        yield ov.phases.init
        ov.argparser.add_argument(flag, action="store_true", dest=dest, help=help)
        yield ov.phases.parse_args
        if getattr(ov.options, dest):
            ov.require(instrument)

    run.instrument = instrument
    return run


@ovld
def parametrized(option: str, type=None, help=None, default=None):  # noqa: F811
    """Decorate an instrument to declare an ``--option``.

    .. code-block:: python

        @parametrized("--xyz", int, "Ex why zee.", 2)
        def instrument_xyz(ov):
            value = ov.options.xyz
            ...

    Arguments:
        option: The name of the option, e.g. ``"--option"``
        type: The type of the option.
        help: Description of the option.
        default: Default value for the option.
        instrument: The instrument to place behind the flag.

    **List of signatures:**
    """
    return partial(parametrized, option, type=type, help=help, default=default)


@ovld
def parametrized(  # noqa: F811
    option: str, instrument: meta(callable), type=None, help=None, default=None
):
    def run(ov):
        yield ov.phases.init
        ov.argparser.add_argument(option, type=type, help=help, default=default)
        yield ov.phases.parse_args
        ov.require(instrument)

    return run


def instrument_definition(fn):
    """Define a parametrizable instrument.

    .. note::
        Such an instrument is parameterized in code and not by command-line flags.

    .. code-block:: python

        @instrument_definition
        def wait_a_bit(ov, seconds):
            yield ov.phases.load_script
            time.sleep(seconds)
            yield ov.phases.run_script

        ...

        wait_five_seconds = wait_a_bit(seconds=5)

        ...

        ov.require(wait_five_seconds)  # <== will be called here

    Arguments:
        fn: The parametrized function. Its first argument, ov, will be given after
            the other arguments.
    """

    @functools.wraps(fn)
    def wrapped(*args, **kwargs):
        def instrument(ov):
            yield from fn(ov, *args, **kwargs)

        return instrument

    return wrapped


def configurable(fn):
    """Create a configurable instrument.

    The instrument must be a function with two parameters: the first one is the
    Overload and the second one must have a type annotation for a dataclass.
    The members of that dataclass will be added to the command-line arguments
    as per :meth:`~voir.argparse_ext.ExtendedArgumentParser.add_from_model`.
    """
    argspec = inspect.getfullargspec(fn)
    argname = argspec.args[1]
    ann = argspec.annotations[argname]

    @functools.wraps(fn)
    def wrapped(ov):
        yield ov.phases.init

        ov.argparser.add_from_model(argname, ann)

        yield ov.phases.parse_args
        yield from fn(ov, getattr(ov.options, argname))

    return wrapped
