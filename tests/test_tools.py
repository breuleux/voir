import pytest

from voir.overseer import Overseer
from voir.tools import gated, parametrized

from .common import program


@pytest.fixture
def ov():
    return Overseer(instruments=[])


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
