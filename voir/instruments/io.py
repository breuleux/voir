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
def io_monitor(ov, poll_interval=10, arch=None):
    """Monitor CPU utilization."""
  
    yield ov.phases.load_script

    def monitor():
        data = {
          str(k): {
            "read_count": diskio.read_count,
            "write_count": diskio.write_count,
            "read_bytes": diskio.read_bytes,
            "read_time": diskio.read_time,
            "write_time": diskio.write_time,
            "busy_time": diskio.busy_time,
          }
            for k, diskio in iocounters.items()
        }
        ov.give(task="main", diskdata=data, time=time.time())

    monitor_thread = Monitor(poll_interval, monitor)
    monitor_thread.start()
    try:
        yield ov.phases.run_script
    finally:
        monitor_thread.stop()
        monitor()
