import os
import sys

from .overseer import Overseer
from .run import collect_instruments, find_voirfiles


def main(argv=None):
    vfs = os.environ.get("VOIRFILE", None)
    if vfs is None:
        vfs = find_voirfiles(".")
    else:
        vfs = vfs.split()
    instruments = collect_instruments(vfs)
    ov = Overseer(instruments=instruments)
    ov(sys.argv[1:] if argv is None else argv)
