"""Monitor IO usage."""

import psutil


def io_monitor(perdisk=False):
    def monitor():
        iocounters = psutil.disk_io_counters(perdisk=perdisk)

        def diskinfo(diskio):
            return {
                "read_count": diskio.read_count,
                "write_count": diskio.write_count,
                "read_bytes": diskio.read_bytes,
                "read_time": diskio.read_time,
                "write_time": diskio.write_time,
                "busy_time": getattr(diskio, "busy_time", None),
            }

        if perdisk:
            return {str(k): diskinfo(diskio) for k, diskio in iocounters.items()}

        return diskinfo(iocounters)

    return monitor
