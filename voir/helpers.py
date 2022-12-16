from contextvars import ContextVar

from giving import give

current_overseer = ContextVar("current_overseer", default=None)


def log(**kwargs):
    ov = current_overseer.get()
    if ov is not None:
        ov.log(kwargs)


def iterate(task: str, iterable, report_batch=False):
    assert isinstance(task, str)
    n = len(iterable)
    with give.inherit(task=task):
        give(progress=(0, n))
        for i, batch in enumerate(iterable):
            if report_batch:
                with give.wrap("step", batch=batch):
                    yield batch
            else:
                yield batch
            give(progress=(i + 1, n))
