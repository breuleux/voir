import fnmatch

from ..tools import instrument_definition


def _keep(patterns):
    optional = [p[1:] for p in patterns if p.startswith("+")]
    patterns = [p for p in patterns if not p.startswith("+")]

    def operation(data):
        result = {}
        ok = False
        for k, v in data.items():
            if k in optional or any(fnmatch.fnmatch(k, p) for p in optional):
                result[k] = v
            if k in patterns or any(fnmatch.fnmatch(k, p) for p in patterns):
                result[k] = v
                ok = True
        return ok and result

    return operation


@instrument_definition
def log(ov, *patterns):
    yield ov.phases.init
    ov.given.map(_keep(patterns)).filter(lambda x: x) >> ov.log
