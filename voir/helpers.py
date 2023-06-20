"""This module defines helper functions that are meant to be used inside programs.

There is typically no reason to use these in a voirfile, but they may be useful in
a script run through Voir.
"""

from contextvars import ContextVar

from giving import give

current_overseer = ContextVar("current_overseer", default=None)


def log(**kwargs):
    """Log key/values directly to the Overseer.

    An :class:`Overseer` typically has two main streams, :attr:`~voir.overseer.Overseer.given`
    and :attr:`~voir.overseer.Overseer.log`. This sends data to the latter, which is
    meant to be exported out of the program, so the datatypes should be serializable.
    """
    ov = current_overseer.get()
    if ov is not None:
        ov.log(kwargs)


def iterate(
    task: str, iterable, report_batch=False, ignore_loading=False, batch_size=None
):
    """Stream events along an iterative process.

    ``iterate`` iterates over the iterable, and while it does so it generates a progress
    report that is accessible from :attr:`~give.overseer.Overseer.given`. For example,
    let us say you have a script and a voirfile defined as follows:

    **script.py:**

    .. code-block:: python

        for x in voir.iterate("count", range(10), report_batch=True):
            print(x)

    **voirfile.py:**

    .. code-block:: python

        def instrument_things(ov):
            yield ov.phases.init

            ov.given.where("progress", task="count").print()

        def enter_exit():
            print("<Enter loop body>")
            yield
            print("<Exit loop body>")

        ov.given.where(task="count").wrap("step", enter_exit)

    You would get the following output:

    .. code-block::

        {'task': 'count', 'progress': (0, 10)}
        <Enter loop body>
        0
        <Exit loop body>
        {'task': 'count', 'progress': (1, 10)}
        <Enter loop body>
        1
        <Exit loop body>

        ...

        {'task': 'count', 'progress': (9, 10)}
        <Enter loop body>
        9
        <Exit loop body>
        {'task': 'count', 'progress': (10, 10)}

    **Compatible instruments:**

    * :func:`voir.instruments.dash<voir.instruments.dash.dash>` displays a graphical progress
      bar from the data provided by ``iterate``.
    * :func:`voir.instruments.rate<voir.instruments.metric.rate>` calculates the rate at which data is
      processed by dividing the number of items per iteration (batch_size) by
      how much time each iteration takes.

    Arguments:
        task: The name of the task that this iteration is doing (e.g. ``"train"`` if
            you are iterating over a training set, or anything else that is representative
            of what you are doing). This is how the data streamed from different calls
            to ``iterate`` can be identified.
        iterable: An arbitrary iterable sequence.
        report_batch: If ``True``, in addition to progress, each time the iterator yields
            a batch, ``iterate`` will wrap its own ``yield`` with
            :meth:`give.wrap("step", batch)<giving.gvr.Giver.wrap>`. Instruments can
            intercept these and do something before and after every batch.
        ignore_loading: If ``True``, (and if ``report_batch`` is also ``True``)
            the step wrapper will ignore any work that is done
            within the iterator (that is to say it will call ``next()`` outside of the
            step).
        batch_size:
            * If ``None``, the ``batch`` will be given.
            * If a function, it will be called on ``batch`` and the result will be
              given as ``batch_size``.
            * If a number, it will be given as ``batch_size`` directly.
    """
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
