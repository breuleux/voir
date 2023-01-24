import operator
import sys
from functools import reduce
from pathlib import Path
from runpy import run_path

from ovld import ovld

module = type(operator)


def find_voirfiles(script_path):
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
    return reduce(operator.add, map(self, value), [])


@ovld
def _to_instruments(self, value: dict):  # noqa: F811
    return reduce(operator.add, map(self, value.values()), [])


@ovld
def _to_instruments(self, value):  # noqa: F811
    return [value]


def _collect_instruments(voirfile, i):
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
    return reduce(
        operator.add,
        [_collect_instruments(vf, i) for i, vf in enumerate(voirfiles)],
        [],
    )
