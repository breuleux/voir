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


def default_batch_size_calc(batch):
    if isinstance(batch, (list, tuple)):
        return len(batch[0])
    else:
        return len(batch)


@instrument_definition
def rate(
    ov,
    interval=1,
    skip=0,
    method=None,
    batch_size_calc=default_batch_size_calc,
    sync=None,
):
    """Compute a rate of computation, in items/s

    The ``rate`` instrument will be triggered by the following calls:

    .. code-block::

        # Method 1: "delta"
        give(task="task_name", batch_size=64)
        give(task="task_name", batch=np.ones((64, 1024, 1024)))
        give(task="task_name", batch=[np.ones((64, 1024, 1024), np.ones((64,))])

        # Method 2: "wrap"
        with giving.wrap("step", task="task_name", batch_size=64):
            ...

        with giving.wrap("step", task="task_name", batch=np.ones((64, 1024, 1024))):
            ...

        with giving.wrap("step", task="task_name", batch_size=None) as data:
            ...
            data["batch_size"] = 64

    In all examples, the batch size will be calculated to be 64. "task_name" is usually
    "train" or "eval".

    In Method 1, the batch size will be divided by the time between two calls to ``give``
    with the same task, yielding the number of items processed by second.

    In Method 2, the batch size will be divided by the time spent inside the ``with``
    statement, again yielding the number of items processed by second.

    See ``voir.iterate`` for an easy interface to this feature:

    .. code-block::

        for x in voir.iterate("train", loader, report_batch=True):
            ...

    Iterate will wrap every iteration of the loop with ``with giving.wrap("step", ...)``.

    Arguments:
        ov: The overseer.
        interval: Either the number of step events between two rate calculations, as an
            int, or the string "Ns" where N is the number of seconds between two rate
            calculations.
        skip: The number of rate calculations to skip (think of it as a warmup period).
        method: Either "delta" or "wrap" depending on whether you want to use Method
            1 or Method 2 as described above.
        batch_size_calc: A function to compute the batch size from the "batch" (e.g.
            ``batch_size_calc=len``). By default, if the batch is a list or a tuple,
            we will assume that it is probably an ``(input, target)`` tuple or something
            of the sort and we take the len of the first element.
        sync: A function to call whenever we want to calculate the rate and which will
            be timed along with the rest. For example, if running on a CUDA GPU, pass
            ``torch.cuda.synchronize`` to ensure that all pending calculations are taken
            into account in the rate calculation.
    """

    yield ov.phases.load_script

    interval_is_time, interval = _parse_duration(interval)

    # Build stream of task/time/batch_size
    if method is None or method == "delta":
        steps_w_batch = ov.given.where("task", "batch", "!batch_size", "!$wrap").kmap(
            task=lambda task: task, batch_size=lambda batch: batch_size_calc(batch)
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
                return {
                    "task": task,
                    "time": seconds,
                    "batch_size": batch_size_calc(data),
                }
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

        if skip:
            times = times.skip(skip)

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
