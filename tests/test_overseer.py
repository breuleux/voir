import os

import pytest

from voir.overseer import JsonlFileLogger

from .common import program


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


def test_probe(ov, capsys, capdata):
    ov.require(_probe)
    ov(["--probe", "//main > greeting", program("hello")])
    assert capsys.readouterr().out == "hello world\n"
    assert '{"greeting": "hello"}' in capdata().split("\n")


def test_hello(ov, capsys, capdata, file_regression):
    ov([program("hello")])
    assert capsys.readouterr().out == "hello world\n"
    file_regression.check(capdata())


def test_collatz(ov, outlines):
    ov([program("collatz"), "-n", "13"])
    results = [int(x) for x in outlines()]
    assert results == [13, 40, 20, 10, 5, 16, 8, 4, 2]


def test_not_serializable(ov, outlines, capdata):
    ov.require(_probe)

    ov(["--probe", "//main > parser", program("collatz"), "-n", "13"])

    results = [int(x) for x in outlines()]
    assert results == [13, 40, 20, 10, 5, 16, 8, 4, 2]

    assert "$unserializable" in capdata()


def test_error_unknown_program(ov, output_summary, file_regression):
    unknown = program("unknown")
    with pytest.raises(FileNotFoundError):
        ov([unknown])

    file_regression.check(output_summary().replace(unknown, "X"))


def test_error_in_load(ov, check_all):
    with pytest.raises(ZeroDivisionError):
        ov([program("zero")])


def test_error_in_run(ov, check_all):
    with pytest.raises(ValueError):
        ov([program("collatz"), "-n", "blah"])


def test_overseer_crash(ov, check_all):
    ov.require(_crash)
    # Should not impede the program's execution
    ov(["--crash", program("collatz"), "-n", "13"])


def test_jsonl_logger_invalid_fd():
    _, w = os.pipe()
    with open(w, "w"):
        pass
    with pytest.raises(OSError):
        JsonlFileLogger(w)

    logger = JsonlFileLogger(w, require_writable=False)
    logger.log({"a": 1, "b": 2})


class Terrible:
    def __str__(self):
        raise Exception()

    __repr__ = __str__


def test_jsonl_logger_bad_str():
    r, w = os.pipe()
    logger = JsonlFileLogger(w)
    logger.log({"a": Terrible()})
    logger.close()
    assert open(r, "r").read() == '{"$unrepresentable": null}\n'
