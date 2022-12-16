import os

import pytest

from voir.forward import GiveToFile


def test_gtf_invalid_fd():
    _, w = os.pipe()
    with open(w, "w"):
        pass
    with pytest.raises(OSError):
        GiveToFile(w)

    gtf = GiveToFile(w, require_writable=False)
    gtf.log({"a": 1, "b": 2})


class Terrible:
    def __str__(self):
        raise Exception()

    __repr__ = __str__


def test_gtf_bad_str():
    r, w = os.pipe()
    gtf = GiveToFile(w)
    gtf.log({"a": Terrible()})
    gtf.close()
    assert open(r, "r").read() == '{"$unrepresentable": null}\n'


def test_multiplexer(run_program):
    run_program(["python", "datafd.py"], info={"index": 1})
