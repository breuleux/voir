from dataclasses import dataclass

from voir.proc import LogEntry, run


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
