import time

import pytest

from voir.instruments.metric import rate

from .common import program


class Collect:
    def __init__(self):
        self.results = []

    def __call__(self, ov):
        yield ov.phases.init

        ov.given.print()
        ov.given["?rate"].map(round) >> self.results.append


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


@pytest.mark.parametrize("interval", [1, 2])
def test_rate(ov, interval, faketime):
    c = Collect()

    ov.require(c)
    ov.require(rate(interval=interval, multimodal_batch=False))

    ov([program("rates")])
    assert c.results == [100] * (10 // interval)


@pytest.mark.parametrize("interval", [1, 2, 5])
def test_sync(ov, interval, faketime):
    def sync():
        time.sleep(0.9)

    c = Collect()

    ov.require(c)
    ov.require(rate(interval=interval, multimodal_batch=False, sync=sync))

    expected_time = 10 * 0.1 + (10 // interval) * 0.9

    ov([program("rates")])
    assert c.results == [round(100 / expected_time)] * (10 // interval)
