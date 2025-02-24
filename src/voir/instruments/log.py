"""Log values automatically from the ``given`` stream."""

import fnmatch

from ..tools import instrument_definition


def _keep(patterns, context):
    """Produce a function that filters a data dictionary with the patterns.

    Returns ``False`` if the data does not match.
    """

    def operation(data):
        result = {}
        ok = False
        for k, v in data.items():
            if k in context or any(fnmatch.fnmatch(k, p) for p in context):
                result[k] = v
            if k in patterns or any(fnmatch.fnmatch(k, p) for p in patterns):
                result[k] = v
                ok = True
        return ok and result

    return operation


@instrument_definition
def log(ov, *patterns, context=[]):
    """Forward data from :attr:`~give.overseer.Overseer.given` into :attr:`~give.overseer.Overseer.log`.

    For each data dictionary in the ``given`` stream, all keys that match at least
    one of the ``patterns`` will be forwarded. If at least one key is forwarded, we also
    forward any keys that are in ``context``.

    For example, if you have this instrument:

    .. code-block:: python

        def instrument_xyz(ov):
            yield ov.phases.init
            ov.require(log("x*", "y", context=["z"]))

    It will affect statements in the main script like this:

    .. code-block:: python

        give(x=2)             # Forwards {"x": 2}
        give(x=2, task=123)   # Forwards {"x": 2, "task": 123}
        give(x=2, a=3)        # Forwards {"x": 2} but not a
        give(xylophone=1)     # Forwards {"xylophone": 1}
        give(a=3)             # Nothing is forwarded
        give(a=3, task=123)   # Nothing is forwarded

    .. note::
        If a patterns start with ``+``, that is equivalent to being in the context
        list, i.e. you can write ``log("x", "+y")`` instead of ``log("x", context="y")``

    Arguments:
        patterns: Patterns for the keys to forward.
        context: Extra keys to forward ONLY IF at least one key matches the patterns.
    """

    if not isinstance(context, (list, tuple)):
        context = [context]

    yield ov.phases.init

    more_context = {p[1:] for p in patterns if p.startswith("+")}
    context = {*more_context, *context}
    patterns = {p for p in patterns if not p.startswith("+")}

    ov.given.map(_keep(patterns, context)).filter(lambda x: x) >> ov.log
