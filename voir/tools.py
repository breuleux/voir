from functools import partial

from ovld import meta, ovld


@ovld
def gated(flag: str):  # noqa: F811
    return partial(gated, flag)


@ovld
def gated(flag: str, doc: str):  # noqa: F811
    return partial(gated, flag, doc=doc)


@ovld
def gated(flag: str, instrument: meta(callable), doc: str = None):  # noqa: F811
    dest = flag

    def run(ov):
        yield ov.phases.init
        ov.argparser.add_argument(flag, action="store_true", dest=dest, help=doc)
        yield ov.phases.parse_args
        if getattr(ov.options, dest):
            ov.require(instrument)

    return run
