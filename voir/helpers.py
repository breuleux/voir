from contextvars import ContextVar

from giving import give

current_overseer = ContextVar("current_overseer", default=None)


def log(**kwargs):
    ov = current_overseer.get()
    if ov is not None:
        ov.log(kwargs)


# def iterate(task: str, iterable, report_batch=False, ignore_loading=False, batch_size=None):
#     assert isinstance(task, str)
#     n = len(iterable)
#     with give.inherit(task=task):
#         give(progress=(0, n))
#         it = iter(enumerate(iterable))
#         while True:
#             def go():
#                 pass

#             try:
#                 i, batch = next(it)
#                 if batch_size is None:
#                     kwargs = {"batch": batch}
#                 elif callable(batch_size):
#                     kwargs = {"batch_size": batch_size(batch)}
#                 else:
#                     kwargs = {"batch_size": batch_size}
#             except StopIteration:
#                 pass

#         for i, batch in enumerate(iterable):
#             if report_batch:
#                 if batch_size is None:
#                     kwargs = {"batch": batch}
#                 elif callable(batch_size):
#                     kwargs = {"batch_size": batch_size(batch)}
#                 else:
#                     kwargs = {"batch_size": batch_size}
#                 if ignore_loading:
#                     with give.wrap("step", **kwargs):
#                         yield batch
#                 else:
#                     give(step=True, **kwargs)
#                     yield batch
#             else:
#                 yield batch
#             give(progress=(i + 1, n))

# def iterate(task: str, iterable, report_batch=False, ignore_loading=False, batch_size=None):
#     assert isinstance(task, str)
#     n = len(iterable)
#     with give.inherit(task=task):
#         give(progress=(0, n))
#         for i, batch in enumerate(iterable):
#             if report_batch:
#                 if batch_size is None:
#                     kwargs = {"batch": batch}
#                 elif callable(batch_size):
#                     kwargs = {"batch_size": batch_size(batch)}
#                 else:
#                     kwargs = {"batch_size": batch_size}
#                 if ignore_loading:
#                     with give.wrap("step", **kwargs):
#                         yield batch
#                 else:
#                     give(step=True, **kwargs)
#                     yield batch
#             else:
#                 yield batch
#             give(progress=(i + 1, n))


# def iterate(task: str, iterable, report_batch=False, ignore_loading=False, batch_size=None):
#     assert isinstance(task, str)
#     n = len(iterable)
#     with give.inherit(task=task):
#         give(progress=(0, n))
#         for i, batch in enumerate(iterable):
#             if report_batch:
#                 with give.wrap("step", batch=batch):
#                     yield batch
#             else:
#                 yield batch
#             give(progress=(i + 1, n))


def iterate(
    task: str, iterable, report_batch=False, ignore_loading=False, batch_size=None
):
    assert isinstance(task, str)
    try:
        n = len(iterable)
    except TypeError:
        n = None

    def prog(i):
        if n is not None:
            give(progress=(i, n))

    i = 0
    with give.inherit(task=task):
        prog(0)
        it = iter(iterable)
        while True:
            if i == n:
                break
            i += 1

            def get_batch():
                batch = next(it)
                if batch_size is None:
                    kwargs = {"batch": batch}
                elif callable(batch_size):
                    kwargs = {"batch_size": batch_size(batch)}
                else:
                    kwargs = {"batch_size": batch_size}
                return batch, kwargs

            try:
                if not report_batch:
                    batch, kwargs = get_batch()
                    yield batch
                elif ignore_loading:
                    batch, kwargs = get_batch()
                    with give.wrap("step", **kwargs):
                        yield batch
                else:
                    empty_kwargs = (
                        {"batch": None} if batch_size is None else {"batch_size": None}
                    )
                    with give.wrap("step", **empty_kwargs) as extra:
                        batch, kwargs = get_batch()
                        extra.update(kwargs)
                        yield batch
            except StopIteration:
                break
            prog(i)
