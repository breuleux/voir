import json
from dataclasses import dataclass

from voir.proc import LogEntry, run
from voir.smuggle import encode_as_escape_sequence


@dataclass
class LogWithIndex(LogEntry):
    index: int = 0


def test_multiplexer(run_program):
    run_program(["python", "datafd.py"], info={"index": 1}, constructor=LogWithIndex)


def test_run():
    results = run(
        ["echo", "hello"], timeout=None, info={"index": 1}, constructor=LogWithIndex
    )
    found = False
    for entry in results:
        assert isinstance(entry, LogWithIndex) and entry.index == 1
        if entry.pipe == "stdout":
            assert entry.data == "hello\n"
            found = True
    assert found


def test_run_stdout():
    secret = {"sekret": True}
    results = run(
        [
            "echo",
            "hello",
            encode_as_escape_sequence(f"{json.dumps(secret)}\n"),
            "world",
        ],
        timeout=None,
        info={"index": 1},
        constructor=LogWithIndex,
        use_stdout=True,
    )
    found = 0
    for entry in results:
        assert isinstance(entry, LogWithIndex) and entry.index == 1
        if entry.pipe == "stdout":
            assert entry.data == "hello  world\n"
            found += 1
        if entry.pipe == "data":
            assert entry.data == secret
            found += 1
    assert found == 2
