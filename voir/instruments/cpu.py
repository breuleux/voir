"""Monitor GPU usage."""

import glob
import os
import time
import traceback

import psutil

from ...tools import instrument_definition
from ..utils import Monitor
from .common import NotAvailable



@instrument_definition
def cpu_monitor(ov, poll_interval=10, arch=None):
    """Monitor CPU utilization."""
  
    yield ov.phases.load_script

    def monitor():
        mem = psutil.virtual_memory()
      
        data = {
            "memory": [
                mem.used,
                mem.total,
            ],
            "load": psutil.cpu_percent(),
        }
        ov.give(task="main", cpudata=data, time=time.time())

    monitor_thread = Monitor(poll_interval, monitor)
    monitor_thread.start()
    try:
        yield ov.phases.run_script
    finally:
        monitor_thread.stop()
        monitor()
