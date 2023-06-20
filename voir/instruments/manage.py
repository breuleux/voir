"""Manage the execution of the program."""

from ..phase import StopProgram
from ..tools import instrument_definition


@instrument_definition
def early_stop(ov, key, n, task=None, signal=StopProgram):
    """Stop the program early after a certain number of events.

    For example, given this code:

    .. code-block:: python

        for i in range(100):
            give(x=i)

    And this instrument in the voirfile:

    .. code-block:: python

        def instrument_xyz(ov):
            yield ov.phases.init
            ov.require(early_stop(key="x", n=20))

    ``voir script.py`` will stop after it has seen the "x" event 20 times, so it will
    only print up to the number 19 and then halt.

    Arguments:
        key: The key to watch for.
        n: The number of events with that key after which to stop.
        task: If not None, filter events where the ``task`` key has this value.
        signal: The exception to raise (defaults to :class:`voir.phase.StopProgram`)
    """
    called = False

    def _stop(value):
        # The stop signal may have the unfortunate effect of creating
        # another event, so this may get called twice.
        nonlocal called
        if not called:
            called = True
            if isinstance(signal, str):
                ov.log({"$event": signal})
            else:
                raise signal(value)

    yield ov.phases.init

    stream = ov.given
    if task is not None:
        stream = stream.where(task=task)
    stream = stream.where(key)
    stream.map_indexed(
        lambda _, idx: {"task": "early_stop", "progress": (idx + 1, n)}
    ).give()
    stream.skip(n) >> _stop
