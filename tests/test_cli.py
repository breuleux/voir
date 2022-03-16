import os
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


def test_environ():
    pipe = subprocess.Popen(
        ["voir", "hello.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env={**os.environ, "VOIRFILE": "voirfile_nested.py"},
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

        assert out == ["~~~~~", "<heyoo>", "hello world", "<bye>"]


def test_dunder_instruments():
    pipe = subprocess.Popen(
        ["voir", "hello.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env={**os.environ, "VOIRFILE": "voirfile_dunder.py"},
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

        assert out == ["<bonjour>", "/////", "hello world", "<bonsoir>"]


def test_forward():
    pipe = subprocess.Popen(
        ["voir", "giver.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env={**os.environ, "VOIRFILE": "voirfile_fw.py"},
        cwd=str(_progdir),
    )
    mr = MultiReader()
    mr.add_process(pipe, {"#proc": "giver"})
    with given() as gv:
        gv.display()
        gv["#proc"].all(lambda x: x == "giver").filter(lambda x: x).fail_if_empty()
        gv["?#return_code"].filter(lambda x: x == 0).fail_if_empty()
        out = gv["?#stdout"].map(str.strip).accum()
        ns = gv["?n"].accum()
        ms = gv["?m"].accum()

        for _ in mr:
            pass

        assert out == ["done", ""]
        assert ns == [0, 1, 2, 100]
        assert ms == []  # Not forwarding m


def test_bad_unicode():
    pipe = subprocess.Popen(
        ["voir", "evil.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        cwd=str(_progdir),
    )
    mr = MultiReader()
    mr.add_process(pipe, {"#proc": "evil"})
    with given() as gv:
        gv.display()
        gv["#proc"].all(lambda x: x == "evil").filter(lambda x: x).fail_if_empty()
        gv["?#return_code"].filter(lambda x: x == 0).fail_if_empty()
        bout = gv["?#binout"].accum()

        for _ in mr:
            pass

        assert bout == [b"\xc3\x28<hey>\n"]
