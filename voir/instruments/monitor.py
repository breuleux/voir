"""Monitor GPU usage."""
import time

from ...tools import instrument_definition
from ..utils import Monitor

from .gpu import new_gpu_monitor
from .cpu import cpu_monitor
from .io import io_monitor
from .network import network_monitor


@instrument_definition
def monitor(ov, poll_interval=10, **monitors):
    """Monitor CPU utilization."""

    yield ov.phases.load_script

    def monitor():
        t = time.time()
        for k, v in monitors.items():
            values = {k: v()}
            ov.give(task="main", time=t, **values)

    monitor_thread = Monitor(poll_interval, monitor)
    monitor_thread.start()
    try:
        yield ov.phases.run_script
    finally:
        monitor_thread.stop()
        monitor()


def monitor_all(ov, poll_interval=10, arch=None):
    return monitor(
        ov,
        poll_interval=poll_interval,
        gpudata=new_gpu_monitor(arch),
        iodata=io_monitor(),
        netdata=network_monitor(),
        cpudata=cpu_monitor(),
    )


def gpu_monitor(ov, poll_interval=10, arch=None):
    return monitor(
        ov,
        poll_interval=poll_interval,
        gpudata=gpu_monitor(arch),
    )
