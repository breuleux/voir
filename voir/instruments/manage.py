from ..phase import StopProgram
from ..tools import instrument_definition


@instrument_definition
def early_stop(ov, key, n, task=None, signal=StopProgram):
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
