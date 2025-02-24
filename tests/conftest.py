import json
import os
import re
import select
from copy import deepcopy
from pathlib import Path

import pytest

from voir.overseer import Overseer

_progdir = Path(__file__).parent / "programs"


@pytest.fixture
def progdir():
    return _progdir


def _format(x):
    idx = x.get("index", 1)
    title = x.pipe or "---"
    content = None
    if x.event == "line":
        content = x.data
    elif x.event == "binary":
        content = f"{x.data}\n"
    elif x.event == "data":
        content = f"{json.dumps(x.data)}\n"
    elif x.event == "start" or x.event == "end":
        title = f"{x.event}\n"
    else:
        title = f"{title}.{x.event}"
        content = f"{json.dumps(x.data)}\n"

    if content:
        return f"#{idx} {title}: {content}"
    else:
        return f"#{idx} {title}"


run_program_template = """Readable
=========
{readable}
Raw
=========
{raw}
"""


order = ["start", "stdout", "stderr", "data", "end"]


def _order_key(entry):
    return order.index(entry.pipe or entry.event)


@pytest.fixture
def run_program(file_regression):
    from voir.proc import Multiplexer

    def run(
        argv, info={}, voirfile=None, env=None, reorder=True, constructor=None, **kwargs
    ):
        if env is None:
            env = os.environ
        if voirfile is not None:
            env = {**os.environ, "VOIRFILE": voirfile}
        mp = Multiplexer(timeout=None, constructor=constructor)
        mp.start(argv, info=info, cwd=_progdir, env=env, buffered=False, **kwargs)
        results = list(mp)
        if reorder:
            results.sort(key=_order_key)
        for r in results:
            # Patch out the times because they will change from a run to the other
            if r.event in ("start", "end"):
                r.data["time"] = "X"

        readable = "".join(_format(deepcopy(x)) for x in results)
        raw = "\n".join(
            x.json() if x.event != "binary" else str(x.dict()) for x in results
        )
        file_regression.check(run_program_template.format(readable=readable, raw=raw))

    return run


@pytest.fixture
def outlines(capsys):
    def read():
        return [x for x in capsys.readouterr().out.split("\n") if x]

    return read


output_summary_template = """##########
# stdout #
##########
{out}
##########
# stderr #
##########
{err}
##########
#  data  #
##########
{data}
"""


@pytest.fixture
def output_summary(capsys, capdata):
    def calc():
        oe = capsys.readouterr()
        dat = capdata()
        txt = output_summary_template.format(out=oe.out, err=oe.err, data=dat)
        txt = re.sub(string=txt, pattern='File "[^"]*", line [0-9]+', repl="<redacted>")
        txt = re.sub(string=txt, pattern=r"[ \^]+\n", repl="")
        return txt

    return calc


@pytest.fixture
def check_all(output_summary, file_regression):
    yield
    file_regression.check(output_summary())


@pytest.fixture
def data_fds():
    r, w = os.pipe()
    yield r, w


@pytest.fixture
def capdata(data_fds):
    r, w = data_fds
    with open(r, "r") as reader:

        def read():
            r, _, _ = select.select([reader], [], [], 0)
            if reader in r:
                return reader.read()
            else:
                return ""

        yield read


@pytest.fixture
def ov(data_fds):
    r, w = data_fds
    return Overseer(instruments=[], logfile=w)


@pytest.fixture
def ov_nodata():
    return Overseer(instruments=[])
