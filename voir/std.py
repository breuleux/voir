from .forward import Forwarder
from .tools import gated, parametrized

instrument_forward_all = gated(
    "--forward-all", Forwarder(), help="Forward stdout/err and given to JSON lines"
)


@parametrized("--forward", help="Forward specified givens to JSON lines")
def instrument_forward(ov):
    yield ov.phases.parse_args
    if ov.options.forward:
        ov.require(Forwarder(fields=ov.options.forward.split(",")))
