from functools import partial

from ovld import meta, ovld


@ovld
def gated(flag: str):  # noqa: F811
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
