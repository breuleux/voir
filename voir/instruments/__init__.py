# We import the instruments lazily
_instruments = {
    "log": "from .log import log",
    "dash": "from .dash import dash",
    "gpu_monitor": "from .gpu import gpu_monitor",
    "rate": "from .metric import rate",
    "early_stop": "from .manage import early_stop",
}


def __getattr__(attr):
    if attr in _instruments:
        exec(_instruments[attr], globals())
        return globals()[attr]
