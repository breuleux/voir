"""Monitor Network usage."""

import psutil


def network_monitor():
    def monitor():
        iocounters = psutil.net_io_counters()

        return {
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

    return monitor
