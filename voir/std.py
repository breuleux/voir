from .forward import Forwarder
from .tools import gated

instrument_forward = gated(
    "--forward", Forwarder(), doc="Forward stdout/err and given to JSON lines"
)
