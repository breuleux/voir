"""Monitor CPU usage."""

from collections import defaultdict

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


def retrieve_process_info(process, acc):
    try:
        io = process.io_counters()
        acc["read_bytes"] += io.read_bytes
        acc["write_bytes"] += io.write_bytes
        acc["read_chars"] += io.read_chars
        acc["write_chars"] += io.write_chars

        mem = process.memory_info()
        acc["mem_used"] += mem.rss

        cpu = process.cpu_percent(interval=1)
        acc["cpu_percent"] += cpu
        acc["children"] += 1
    except psutil.AccessDenied:
        pass
    except psutil.NoSuchProcess:
        pass


def _recursive(process, acc):
    for child in process.children(recursive=True):
        retrieve_process_info(child, acc)


def process_monitor(pid, recursive=True):
    process = psutil.Process(pid)
    cpu_count = psutil.cpu_count()
    mem_total = psutil.virtual_memory()

    def monitor():
        nonlocal process
        acc = defaultdict(float)

        with process.oneshot():
            cpu_num = process.cpu_num()
            retrieve_process_info(process, acc)
            if recursive:
                _recursive(process, acc)

        return {
            "pid": pid,
            # CPU
            "load": acc["cpu_percent"] / cpu_count,
            "num": cpu_num,
            # IO
            "read_bytes": acc["read_bytes"],
            "write_bytes": acc["write_bytes"],
            # Fake IO
            "read_chars": acc["read_chars"],
            "write_chars": acc["write_chars"],
            # Memory
            "memory": [acc["mem_used"], mem_total.total],
        }

    return monitor
