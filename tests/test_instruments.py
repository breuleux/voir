import time

import pytest

from voir.instruments.gpu import (
    NotAvailable,
    get_backends,
    get_gpu_info,
    select_backend,
)
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
    ov.require(rate(interval=interval, batch_size_calc=len))

    ov([program("rates")])
    assert c.results == [100] * (10 // interval)


@pytest.mark.parametrize("interval", [1, 2, 5])
def test_sync(ov, interval, faketime):
    def sync():
        time.sleep(0.9)

    c = Collect()

    ov.require(c)
    ov.require(rate(interval=interval, batch_size_calc=len, sync=sync))

    expected_time = 10 * 0.1 + (10 // interval) * 0.9

    ov([program("rates")])
    assert c.results == [round(100 / expected_time)] * (10 // interval)


def test_gpu_backend():
    assert list(sorted(get_backends())) == ["cpu", "cuda", "hpu", "rocm", "xpu"]


def test_gpu_info_cpu():
    assert get_gpu_info() == {"arch": "cpu", "gpus": {}}


def test_select_backend_rocm():
    with pytest.raises(NotAvailable):
        select_backend("rocm")


def test_select_backend_cuda():
    with pytest.raises(NotAvailable):
        select_backend("cuda")
