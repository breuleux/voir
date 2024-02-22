"""Monitor CPU usage."""

import psutil


def cpu_monitor():
    def monitor():
        mem = psutil.virtual_memory()

        return {
            "memory": [
                mem.used,
                mem.total,
            ],
            "load": psutil.cpu_percent(),
        }

    return monitor
