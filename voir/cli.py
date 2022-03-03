from coleo import auto_cli, default, Option

from ptera import no_overlay

from .utils import fetch, resolve
from .overseer import run_script


def main():
    auto_cli(run)


def run():
    # Instrumenting functions
    # [alias: -i]
    # [action: append]
    instrument: Option = default([])

    # Probe(s) to bridge data collection
    # [alias: -p]
    # [action: append]
    probe: Option = default([])

    # Path to the script
    # [positional]
    script: Option

    # Arguments to the script
    # [positional: --]
    args: Option

    script, field, _ = resolve(script, "__main__")

    instruments = dict(fetch(inst) for inst in instrument)

    if probe:
        instruments.update({p: {} for p in probe})

    with no_overlay():
        run_script(
            script=script,
            field=field,
            argv=args,
            instruments=instruments,
        )
