import os
import re
import select
from pathlib import Path

import pytest

from voir.overseer import Overseer
from voir.tools import gated, parametrized

_progdir = Path(__file__).parent / "programs"


def _program(name):
    return str(_progdir / f"{name}.py")


@pytest.fixture
def outlines(capsys):
    def read():
        return [x for x in capsys.readouterr().out.split("\n") if x]

    return read


template = """##########
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
        txt = template.format(out=oe.out, err=oe.err, data=dat)
        txt = re.sub(string=txt, pattern='File "[^"]*", line [0-9]+', repl="<redacted>")
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


def _probe(ov):
    yield ov.phases.init
    ov.argparser.add_argument("--probe")
    yield ov.phases.load_script
    if ov.options.probe:
        ov.probe(ov.options.probe) >> ov.log


def _crash(ov):
    yield ov.phases.init
    ov.argparser.add_argument("--crash", action="store_true")
    yield ov.phases.load_script
    if ov.options.crash:
        raise ValueError("boom.")


@pytest.fixture
def ov(data_fds):
    r, w = data_fds
    return Overseer(instruments=[_probe, _crash], logfile=w)


@pytest.fixture
def ov_nodata():
    return Overseer(instruments=[_probe, _crash])


def test_probe(ov, capsys, capdata):
    ov(["--probe", "//main > greeting", _program("hello")])
    assert capsys.readouterr().out == "hello world\n"
    assert '{"greeting": "hello"}' in capdata().split("\n")


def test_hello(ov, capsys, capdata, file_regression):
    ov([_program("hello")])
    assert capsys.readouterr().out == "hello world\n"
    file_regression.check(capdata())


@gated("--wow")
def wow(ov):
    yield ov.phases.run_script
    print("WOW!")


def test_hello_flags_on(ov_nodata, outlines):
    ov_nodata.require(wow)
    ov_nodata(["--wow", _program("hello")])
    assert outlines() == ["hello world", "WOW!"]


def test_hello_flags_off(ov_nodata, outlines):
    ov_nodata.require(wow)
    ov_nodata([_program("hello")])
    assert outlines() == ["hello world"]


@gated("--wow", "Turn on the WOW")
def wow2(ov):
    yield ov.phases.run_script
    print("WOW!")


def test_gated_with_doc(ov, outlines):
    ov.require(wow2)
    ov(["--wow", _program("hello")])
    assert outlines() == ["hello world", "WOW!"]


@parametrized("--funk", type=int, help="How much funk?")
def funk(ov):
    yield ov.phases.run_script
    for i in range(ov.options.funk):
        print("F U N K!")


def test_parametrized(ov, outlines):
    ov.require(funk)
    ov(["--funk", "3", _program("hello")])
    assert outlines() == [
        "hello world",
        "F U N K!",
        "F U N K!",
        "F U N K!",
    ]


def test_collatz(ov, outlines):
    ov([_program("collatz"), "-n", "13"])
    results = [int(x) for x in outlines()]
    assert results == [13, 40, 20, 10, 5, 16, 8, 4, 2]


def test_not_serializable(ov, outlines, capdata):
    ov(["--probe", "//main > parser", _program("collatz"), "-n", "13"])

    results = [int(x) for x in outlines()]
    assert results == [13, 40, 20, 10, 5, 16, 8, 4, 2]

    assert "#unserializable" in capdata()


def test_error_unknown_program(ov, output_summary, file_regression):
    unknown = _program("unknown")
    with pytest.raises(FileNotFoundError):
        ov([unknown])

    file_regression.check(output_summary().replace(unknown, "X"))


def test_error_in_load(ov, check_all):
    with pytest.raises(ZeroDivisionError):
        ov([_program("zero")])


def test_error_in_run(ov, check_all):
    with pytest.raises(ValueError):
        ov([_program("collatz"), "-n", "blah"])


def test_overseer_crash(ov, check_all):
    # Should not impede the program's execution
    ov(["--crash", _program("collatz"), "-n", "13"])
