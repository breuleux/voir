from pathlib import Path

import pytest

from voir.forward import Forwarder, JSONSerializer
from voir.overseer import Overseer
from voir.tools import gated

_progdir = Path(__file__).parent / "programs"


def _program(name):
    return str(_progdir / f"{name}.py")


def _probe(ov):
    yield ov.phases.init
    ov.argparser.add_argument("--probe")
    yield ov.phases.load_script
    if ov.options.probe:
        ov.probe(ov.options.probe).give()


@pytest.fixture
def ov():
    ser = JSONSerializer()
    results = []

    def _write(entry):
        results.append(ser.loads(entry))

    ov = Overseer(
        instruments=[
            Forwarder(write=_write),
            _probe,
        ]
    )
    ov.results = results
    return ov


def test_probe(ov):
    ov(["--probe", "//main > greeting", _program("hello")])
    assert ov.results == [
        {"greeting": "hello"},
        {"#stdout": "hello world"},
        {"#stdout": "\n"},
    ]


def test_hello(ov):
    ov([_program("hello")])
    assert ov.results == [
        {"#stdout": "hello world"},
        {"#stdout": "\n"},
    ]


@gated("--wow")
def wow(ov):
    yield ov.phases.run_script
    print("WOW!")


def test_hello_flags_on(ov):
    ov.require(wow)
    ov(["--wow", _program("hello")])
    assert ov.results == [
        {"#stdout": "hello world"},
        {"#stdout": "\n"},
        {"#stdout": "WOW!"},
        {"#stdout": "\n"},
    ]


def test_hello_flags_off(ov):
    ov.require(wow)
    ov([_program("hello")])
    assert ov.results == [
        {"#stdout": "hello world"},
        {"#stdout": "\n"},
    ]


def test_collatz(ov):
    ov([_program("collatz"), "-n", "13"])
    results = [x["#stdout"] for x in ov.results]
    results = [int(x) for x in results if x != "\n"]
    assert results == [13, 40, 20, 10, 5, 16, 8, 4, 2]


def test_not_serializable(ov):
    ov(["--probe", "//main > parser", _program("collatz"), "-n", "13"])
    assert list(ov.results[0].keys()) == ["#unserializable"]
    results = [x["#stdout"] for x in ov.results[1:]]
    results = [int(x) for x in results if x != "\n"]
    assert results == [13, 40, 20, 10, 5, 16, 8, 4, 2]


def test_error_unknown_program(ov):
    ov([_program("unknown")])
    assert ov.results[0] == {"#stderr": "An error occurred"}
    assert "FileNotFoundError" in str(ov.results)


def test_error_in_load(ov):
    ov([_program("zero")])
    assert ov.results[0] == {"#stderr": "An error occurred"}
    assert "ZeroDivisionError" in str(ov.results)


def test_error_in_run(ov):
    ov([_program("collatz"), "-n", "blah"])
    assert ov.results[0] == {"#stderr": "An error occurred"}
    assert "ValueError" in str(ov.results)
