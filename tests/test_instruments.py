import time

import pytest

from voir.instruments import rate

from .common import program


@pytest.fixture
def faketime(monkeypatch):
    current_time = [0]

    def sleep(n):
        current_time[0] += n

    def nano():
        return current_time[0] * 1_000_000_000

    monkeypatch.setattr(time, "sleep", sleep)
    monkeypatch.setattr(time, "time", lambda: current_time[0])
    monkeypatch.setattr(time, "time_ns", nano)


def test_rate(ov, faketime):
    results = []

    @ov.require
    def collect(ov):
        yield ov.phases.init

        ov.given.print()
        ov.given["?rate"].map(round) >> results.append

    ov.require(rate(interval=1, multimodal_batch=False))

    ov([program("rates")])
    assert results == [100] * 10
