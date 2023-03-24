from giving import given

from voir.helpers import iterate
from voir.overseer import Overseer

from .common import program


def print_given(ov):
    yield ov.phases.init
    ov.given.print()


def test_iterate_program(check_all):
    ov = Overseer(instruments=[print_given])
    ov([program("iterate"), "0"])


def test_iterate_program_report_batch(check_all):
    ov = Overseer(instruments=[print_given])
    ov([program("iterate"), "1"])


def test_log(check_all, data_fds):
    _, w = data_fds
    ov = Overseer(instruments=[], logfile=w)
    ov([program("log")])


def _extractor(key):
    def xtract():
        return (yield)[key]

    return xtract


def test_iterate_batch_size():
    with given() as gv:
        bs = gv.wmap("step", _extractor("batch_size")).accum()
        gv.display()
        for _ in iterate("x", range(10), report_batch=True, batch_size=3):
            pass

    assert bs == [3] * 10


def test_iterate_batch_size_fn():
    with given() as gv:
        bs = gv.wmap("step", _extractor("batch_size")).accum()
        gv.display()
        for _ in iterate("x", range(10), report_batch=True, batch_size=lambda x: x + 1):
            pass

    assert bs == list(range(1, 11))


def test_iterate_no_length():
    def generate():
        for x in range(10):
            yield x

    with given() as gv:
        bs = gv.wmap("step", _extractor("batch_size")).accum()
        gv.display()
        for _ in iterate(
            "x", generate(), report_batch=True, batch_size=lambda x: x + 1
        ):
            pass

    assert bs == list(range(1, 11)) + [None]
