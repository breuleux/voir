"""Monitor GPU usage."""
import time

from ..tools import instrument_definition
from .utils import Monitor, monitor as generic_monitor

from .gpu import gpu_monitor as gpu_monitor_fun, select_backend
from .cpu import cpu_monitor
from .io import io_monitor
from .network import network_monitor


def monitor(ov, poll_interval=10, worker_init=None, **monitors):
    """Monitor CPU utilization."""

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
        process=True,
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
        gpudata=gpu_monitor_fun(arch),
        iodata=io_monitor(),
        netdata=network_monitor(),
        cpudata=cpu_monitor(),
        worker_init=lambda: select_backend(arch, force=True)
    )


def gpu_monitor(ov, poll_interval=10, arch=None):
    return monitor(
        ov,
        poll_interval=poll_interval,
        gpudata=gpu_monitor_fun(arch),
    )
