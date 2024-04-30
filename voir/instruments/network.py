"""Monitor Network usage."""

import psutil


def network_monitor(pernic=False):
    def monitor():
        iocounters = psutil.net_io_counters(pernic=pernic)

        def netinfo(netio):
            return {
                "bytes_sent": netio.bytes_sent,
                "bytes_recv": netio.bytes_recv,
                "packets_sent": netio.packets_sent,
                "packets_recv": netio.packets_recv,
                "errin": netio.errin,
                "errout": netio.errout,
                "dropin": netio.dropin,
                "dropout": netio.dropout,
            }

        if pernic:
            return {str(k): netinfo(netio) for k, netio in iocounters.items()}

        return netinfo(iocounters)

    return monitor
