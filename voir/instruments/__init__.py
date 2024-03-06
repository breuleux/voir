"""Standard instruments.

Instruments can be imported directly from ``voir.instruments``, but they are
defined in their own files that are imported lazily.
"""

# We import the instruments lazily
_instruments = {
    "log": "from .log import log",
    "dash": "from .dash import dash",
    "gpu_monitor": "from .monitor import gpu_monitor",
    "monitor_all": "from .monitor import monitor_all",
    "rate": "from .metric import rate",
    "early_stop": "from .manage import early_stop",
}


def __getattr__(attr):
    if attr in _instruments:
        exec(_instruments[attr], globals())
        return globals()[attr]
