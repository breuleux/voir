"""Monitor IO usage."""

import psutil


def io_monitor():
    def monitor():
        iocounters = psutil.disk_io_counters()

        return {
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

    return monitor
