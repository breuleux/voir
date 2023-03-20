import pytest


@pytest.mark.parametrize("prelude", (["voir"], ["python", "-m", "voir"]))
def test_cli(prelude, run_program):
    run_program([*prelude, "hello.py"])


def test_cli_dash_m(run_program):
    run_program(["voir", "-m", "hello:alt"])


def test_cli_package(run_program):
    run_program(["voir", "-m", "packpack"])


def test_environ(run_program):
    run_program(["voir", "hello.py"], voirfile="voirfile_nested.py")


def test_dunder_instruments(run_program):
    run_program(["voir", "hello.py"], voirfile="voirfile_dunder.py")


def test_forward(run_program):
    run_program(["voir", "giver.py"], voirfile="voirfile_fw.py")


def test_bad_unicode(run_program):
    run_program(["voir", "evil.py"])
