from pathlib import Path

_progdir = Path(__file__).parent / "programs"


def program(name):
    return str(_progdir / f"{name}.py")
