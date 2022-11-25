import os
import sys

import pkg_resources

from .overseer import Overseer
from .run import collect_instruments, find_voirfiles


def collect_contrib_instruments():
    results = []
    for entry_point in pkg_resources.iter_entry_points("voir.instrument"):
        results.append(entry_point.load())
    return results


def main(argv=None):
    sys.path.insert(0, os.path.abspath(os.curdir))

    vfs = os.environ.get("VOIRFILE", None)
    if vfs is None:
        vfs = find_voirfiles(".")
    else:
        vfs = vfs.split()

    instruments = collect_instruments(vfs)
    instruments.extend(collect_contrib_instruments())

    ov = Overseer(instruments=instruments, logfile=int(os.environ.get("DATA_FD", 3)))
    ov(sys.argv[1:] if argv is None else argv)
