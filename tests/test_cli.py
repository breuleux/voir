import subprocess
from pathlib import Path

import pytest
from giving import given

from voir.forward import MultiReader

_progdir = Path(__file__).parent / "programs"


@pytest.mark.parametrize("prelude", (["voir"], ["python", "-m", "voir"]))
def test_cli(prelude):
    pipe = subprocess.Popen(
        [*prelude, "hello.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        cwd=str(_progdir),
    )
    mr = MultiReader()
    mr.add_process(pipe, {"#proc": "hello"})
    with given() as gv:
        gv.display()
        gv["#proc"].all(lambda x: x == "hello").filter(lambda x: x).fail_if_empty()
        gv["?#return_code"].filter(lambda x: x == 0).fail_if_empty()
        out = gv["?#stdout"].map(str.strip).accum()

        for _ in mr:
            pass

        assert out == ["<hey>", "hello world", "<bye>"]
