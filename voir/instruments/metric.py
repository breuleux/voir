import time
from typing import Union

from giving import Given
from ovld import ovld

from ..tools import instrument_definition


@ovld
def _parse_duration(x: Union[int, float]):
    return (False, x)


@ovld
def _parse_duration(x: str):  # noqa: F811
    if x.endswith("s"):
        return (True, float(x[:-1]))
    else:
        return (False, float(x))


@instrument_definition
def rate(ov, interval=1, method=None, multimodal_batch=True, sync=None):

    if multimodal_batch:

        def _batchsize(batch):
            if isinstance(batch, (list, tuple)):
                return len(batch[0])
            else:
                return len(batch)

    else:
        _batchsize = len

    yield ov.phases.load_script

    interval_is_time, interval = _parse_duration(interval)

    # Build stream of task/time/batch_size
    if method is None or method == "step":
        steps_w_batch = ov.given.where("task", "batch", "!batch_size", "!$wrap").kmap(
            task=lambda task: task, batch_size=lambda batch: _batchsize(batch)
        )
        steps_w_batch_size = ov.given.where("task", "batch_size", "!$wrap")
        times = times_step = (
            (steps_w_batch | steps_w_batch_size)
            .augment(time=lambda: time.time_ns())
            .pairwise()
            .starmap(
                lambda x, y: {
                    "task": y["task"],
                    "time": (y["time"] - x["time"]) / 1_000_000_000,
                    "batch_size": y["batch_size"],
                }
            )
        )

    if method is None or method == "wrap":

        def _timewrap():
            t0 = time.time_ns()
            results = yield
            t1 = time.time_ns()
            task = results["task"]
            if "batch_size" in results:
                bs = results["batch_size"]
                if bs is None:
                    return None
                seconds = (t1 - t0) / 1_000_000_000
                return {
                    "task": task,
                    "time": seconds,
                    "batch_size": bs,
                }
            elif "batch" in results:
                data = results["batch"]
                if data is None:
                    return None
                seconds = (t1 - t0) / 1_000_000_000
                return {"task": task, "time": seconds, "batch_size": _batchsize(data)}
            else:
                return None

        times = times_wrap = ov.given.wmap("step", _timewrap).filter(lambda x: x)

    if method is None:
        times = times_step | times_wrap

    grouped_by_task = times.group_by(lambda data: data["task"])

    @grouped_by_task.subscribe
    def setup_pipeline(times):
        times = Given(_obs=times)

        # Group by interval
        if interval_is_time:
            times = times.buffer_with_time(interval)
        else:
            times = times.buffer_with_count(interval)

        # Compute the final metric
        @times.subscribe
        def _(elems):
            t = 0
            if sync is not None:
                t0 = time.time_ns()
                sync()
                t1 = time.time_ns()
                t += (t1 - t0) / 1_000_000_000

            t += sum(e["time"] for e in elems)
            n = sum(e["batch_size"] for e in elems)

            if n and t:
                ov.give(rate=n / t, units="items/s", task=elems[0]["task"])
