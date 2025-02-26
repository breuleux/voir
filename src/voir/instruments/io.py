"""Monitor IO usage."""

import psutil


def io_monitor(perdisk=False):
    start = psutil.disk_io_counters(perdisk=perdisk)
    busy_time = getattr(start, "busy_time", 0)

    def monitor():
        iocounters = psutil.disk_io_counters(perdisk=perdisk)

        def diskinfo(diskio):
            return {
                "read_count": diskio.read_count - start.read_count,
                "write_count": diskio.write_count - start.write_count,
                "read_bytes": diskio.read_bytes - start.read_bytes,
                "read_time": diskio.read_time - start.read_time,
                "write_time": diskio.write_time - start.write_time,
                "busy_time": getattr(diskio, "busy_time", 0) - busy_time,
            }

        if perdisk:
            return {str(k): diskinfo(diskio) for k, diskio in iocounters.items()}

        return diskinfo(iocounters)

    return monitor
