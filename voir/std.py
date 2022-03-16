from .forward import Forwarder
from .tools import gated

instrument_forward = gated(
    "--forward", Forwarder(), help="Forward stdout/err and given to JSON lines"
)
