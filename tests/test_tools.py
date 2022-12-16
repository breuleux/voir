from dataclasses import dataclass

from voir.tools import configurable, gated, instrument_definition, parametrized

from .common import program


@gated("--wow")
def wow(ov):
    yield ov.phases.run_script
    print("WOW!")


def test_hello_flags_on(ov, outlines):
    ov.require(wow)
    ov(["--wow", program("hello")])
    assert outlines() == ["hello world", "WOW!"]


def test_hello_flags_off(ov, outlines):
    ov.require(wow)
    ov([program("hello")])
    assert outlines() == ["hello world"]


@gated("--wow", "Turn on the WOW")
def wow2(ov):
    yield ov.phases.run_script
    print("WOW!")


def test_gated_with_doc(ov, outlines):
    ov.require(wow2)
    ov(["--wow", program("hello")])
    assert outlines() == ["hello world", "WOW!"]


@parametrized("--funk", type=int, help="How much funk?")
def funk(ov):
    yield ov.phases.run_script
    for i in range(ov.options.funk):
        print("F U N K!")


def test_parametrized(ov, outlines):
    ov.require(funk)
    ov(["--funk", "3", program("hello")])
    assert outlines() == [
        "hello world",
        "F U N K!",
        "F U N K!",
        "F U N K!",
    ]


@instrument_definition
def instrument1(ov, x, y, z):
    yield ov.phases.init
    ov.log({"x": x, "y": y, "z": z})


def test_instrument_definition(ov, check_all):
    ov.require(instrument1(5, 6, 7))
    ov([program("hello")])


@dataclass
class Configuration:
    x: bool = True
    zazz: int = 4


@configurable
def instrument2(ov, cfg: Configuration):
    yield ov.phases.init
    ov.log({"x": cfg.x, "zazz": cfg.zazz})


def test_configurable(ov, check_all):
    ov.require(instrument2)
    ov([program("hello")])


def test_configurable2(ov, check_all):
    ov.require(instrument2)
    ov(["--no-x", "--zazz", "89", program("hello")])


def test_configurable3(ov, progdir, check_all):
    ov.require(instrument2)
    ov(["--config", str(progdir / "cfg.yaml"), program("hello")])


def test_configurable4(ov, progdir, check_all):
    ov.require(instrument2)
    ov(["--config", str(progdir / "cfg.yaml"), "-x", program("hello")])
