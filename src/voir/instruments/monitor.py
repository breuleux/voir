"""Monitor GPU usage."""

import time

from ..tools import instrument_definition
from .cpu import cpu_monitor
from .gpu import gpu_monitor as gpu_monitor_fun, select_backend
from .io import io_monitor
from .network import network_monitor
from .utils import monitor as generic_monitor


def monitor(ov, poll_interval=10, worker_init=None, **monitors):
    """Monitor metrics given by monitors"""

    yield ov.phases.load_script

    def get():
        t = time.time()
        entries = []
        for k, v in monitors.items():
            values = {
                "task": "main",
                "time": t,
                k: v(),
            }
            entries.append(values)
        return entries

    def push(data):
        for entry in data:
            ov.give(**entry)

    mon = generic_monitor(
        poll_interval,
        get,
        push,
        process=False,
        worker_init=worker_init,
    )
    mon.start()
    try:
        yield ov.phases.run_script
    finally:
        mon.stop()


@instrument_definition
def monitor_all(ov, poll_interval=10, arch=None):
    return monitor(
        ov,
        poll_interval=poll_interval,
        gpudata=gpu_monitor_fun(),
        iodata=io_monitor(),
        netdata=network_monitor(),
        cpudata=cpu_monitor(),
        worker_init=lambda: select_backend(arch, force=True),
    )


@instrument_definition
def gpu_monitor(ov, poll_interval=10, arch=None):
    """Monitor GPU utilization.

    Supports monitoring CUDA (NVIDIA) and ROCm (AMD) architectures.

    The following data is monitored:

    .. code-block:: javascript

        {
            "memory": [USED, TOTAL],  // In MB
            "load": LOAD,             // Utilization, from 0 to 1
            "temperature": TEMP,      // In celsius
            "power": POWER,
        }

    This data structure is added to the :meth:`~voir.overseer.Overseer.given` stream
    as follows:

    .. code-block:: python

        give(task="main", gpudata=DATA)

    Arguments:
        poll_interval: The polling interval, in seconds. Data will be produced
            every poll_interval seconds.
        arch: The GPU architecture to monitor. If None, the architecture will be
            deduced automatically.
    """
    return monitor(
        ov,
        poll_interval=poll_interval,
        gpudata=gpu_monitor_fun(),
        worker_init=lambda: select_backend(arch, force=True),
    )
