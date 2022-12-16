from voir.overseer import Overseer

from .common import program


def print_given(ov):
    yield ov.phases.init
    ov.given.print()


def test_iterate(check_all):
    ov = Overseer(instruments=[print_given])
    ov([program("iterate"), "0"])


def test_iterate_report_batch(check_all):
    ov = Overseer(instruments=[print_given])
    ov([program("iterate"), "1"])


def test_log(check_all, data_fds):
    _, w = data_fds
    ov = Overseer(instruments=[], logfile=w)
    ov([program("log")])
