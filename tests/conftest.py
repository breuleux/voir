import json
import os
from copy import deepcopy
from pathlib import Path

import pytest

_progdir = Path(__file__).parent / "programs"


@pytest.fixture
def progdir():
    return _progdir


def _format(thing):
    idx = thing.pop("index", 1)
    title = thing.pop("#pipe", "---")
    evt = thing["#event"]
    data = thing["#data"]
    content = None
    if evt == "line":
        content = data
    elif evt == "binary":
        content = f"{data}\n"
    elif evt == "data":
        subevt = data.pop("#event", None)
        if subevt is not None:
            title = f"{title}.{subevt.pop('type')}"
            content = f"{json.dumps(subevt)}\n"
        else:
            content = f"{json.dumps(data)}\n"
    elif evt == "start" or evt == "end":
        title = f"{evt}\n"
    else:
        content = f"{str(thing)}\n"

    if content:
        return f"#{idx} {title}: {content}"
    else:
        return f"#{idx} {title}"


template = """Readable
=========
{readable}
Raw
=========
{raw}
"""


order = ["start", "stdout", "stderr", "data", "end"]


def _order_key(entry):
    return order.index(entry.get("#pipe", entry["#event"]))


@pytest.fixture
def run_program(file_regression):
    from voir.forward import Multiplexer

    def run(argv, info={}, voirfile=None, env=None, reorder=True, **kwargs):
        if env is None:
            env = os.environ
        if voirfile is not None:
            env = {**os.environ, "VOIRFILE": voirfile}
        mp = Multiplexer(timeout=None)
        mp.run(argv, info=info, cwd=_progdir, env=env, **kwargs)
        results = list(mp)
        if reorder:
            results.sort(key=_order_key)
        for r in results:
            # Patch out the times because they will change from a run to the other
            if r["#event"] in ("start", "end"):
                r["#data"]["time"] = "X"

        readable = "".join(_format(deepcopy(x)) for x in results)
        raw = "\n".join(
            json.dumps(x) if x["#event"] != "binary" else str(x) for x in results
        )
        file_regression.check(template.format(readable=readable, raw=raw))

    return run
