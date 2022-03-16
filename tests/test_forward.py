import pytest

from voir.forward import JSONSerializer


@pytest.fixture
def jser():
    return JSONSerializer()


class X:
    def __str__(self):
        return "<X str>"

    def __repr__(self):
        return "<X repr>"


def test_deserialize(jser):
    assert jser.loads('{"a": 1}') == {"a": 1}


def test_serialize(jser):
    assert jser.dumps({"a": 1}) == '{"a": 1}'


def test_deserialize_nondict(jser):
    assert jser.loads("123") == {"#data": 123}


def test_unserializable(jser):
    assert jser.dumps(X()) == '{"#unserializable": "{\'#data\': <X repr>}"}'


def test_undeserializable(jser):
    assert jser.loads("InVaLiD") == {"#undeserializable": "InVaLiD"}
