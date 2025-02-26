"""Command-line interface."""

import operator
import os
import sys
from functools import reduce
from pathlib import Path
from runpy import run_path

from ovld import ovld

from .overseer import Overseer

module = type(operator)


def find_voirfiles(script_path):
    """Find voirfiles that should be active for a given script.

    This proceeds by looking for ``voirfile.py`` in the directory and its
    parents.

    Arguments:
        script_path: The script's path.
    """
    script_path = Path(script_path).expanduser().absolute()
    cur = script_path

    if cur.is_file():  # pragma: no cover
        # Currently not used
        cur = cur.parent
        vf = (cur / script_path.stem).with_suffix(".voirfile.py")
        results = [vf]
    else:
        results = []

    while cur != cur.parent:
        results.append(cur / "voirfile.py")
        cur = cur.parent

    return [str(pth) for pth in results if pth.exists()]


@ovld
def _to_instruments(self, value: list):  # noqa: F811
    """Recursively find instruments in a data structure."""
    return reduce(operator.add, map(self, value), [])


@ovld
def _to_instruments(self, value: dict):  # noqa: F811
    return reduce(operator.add, map(self, value.values()), [])


@ovld
def _to_instruments(self, value):  # noqa: F811
    return [value]


def _collect_instruments(voirfile, i):
    """Collect instruments from a single voirfile.

    Arguments:
        voirfile: The path to the voirfile.
        i: An integer that determines the module name under which we will
           load the voirfile (``__voir0__``, ``__voir1__``, etc. because
           we want them to all coexist while avoiding clashes).
    """
    name = "__voir__" if i == 0 else f"__voir{i}__"
    md = module(name)
    md.__file__ = voirfile
    glb = run_path(voirfile, init_globals=vars(md), run_name=name)
    sys.modules[name] = md
    pfx = "instrument_"
    if "__instruments__" in glb:
        return _to_instruments(glb["__instruments__"])
    else:
        results = []
        for name, value in glb.items():
            if name.startswith(pfx):
                results.extend(_to_instruments(value))
        return results


def collect_instruments(voirfiles):
    """Collect instruments from a list of voirfiles.

    Arguments:
        voirfiles: List of files in which to find instruments.
    """
    return reduce(
        operator.add,
        [_collect_instruments(vf, i) for i, vf in enumerate(voirfiles)],
        [],
    )


def collect_contrib_instruments():
    """Collect instruments declared as entry points.

    This isn't really used, currently.
    """
    try:
        import pkg_resources

        results = []
        for entry_point in pkg_resources.iter_entry_points("voir.instrument"):
            results.append(entry_point.load())
        return results
    except ImportError:
        return []


def main(argv=None):
    """Entry point of the voir command line interface."""
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
