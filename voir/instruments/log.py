import fnmatch

from ..tools import instrument_definition


def _keep(patterns, context):
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
    if not isinstance(context, (list, tuple)):
        context = [context]

    yield ov.phases.init

    more_context = {p[1:] for p in patterns if p.startswith("+")}
    context = {*more_context, *context}
    patterns = {p for p in patterns if not p.startswith("+")}

    ov.given.map(_keep(patterns, context)).filter(lambda x: x) >> ov.log
