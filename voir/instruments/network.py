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
def network_monitor(ov, poll_interval=10, arch=None):
    """Monitor network utilization."""
  
    yield ov.phases.load_script

    def monitor():
        iocounters = psutil.net_io_counters()
      
        data = {
          str(k): {
            "bytes_sent": netio.bytes_sent,
            "bytes_recv": netio.bytes_recv,
            "packets_sent": netio.packets_sent,
            "packets_recv": netio.packets_recv,
            "errin": netio.errin,
            "errout": netio.errout,
            "dropin": netio.dropin,
            "dropout": netio.dropout,
          }
            for k, netio in iocounters.items()
        }
        ov.give(task="main", netdata=data, time=time.time())

    monitor_thread = Monitor(poll_interval, monitor)
    monitor_thread.start()
    try:
        yield ov.phases.run_script
    finally:
        monitor_thread.stop()
        monitor()
