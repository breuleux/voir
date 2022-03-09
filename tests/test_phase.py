import pytest

from voir.phase import PhaseRunner


class LightOverseer:
    def __init__(self):
        self.results = []
        self.errors = []
        self.error_values = []
        self.pr = PhaseRunner(
            ["one", "two", "three", "four"],
            args=[self, self.results],
            kwargs={},
            error_handler=self._on_error,
        )
        self.phases = self.pr.phases
        self.add = self.pr.add

    def _on_error(self, err):
        if isinstance(err, AssertionError):
            raise
        self.error_values.append(err)
        self.errors.append(type(err))

    def _run_phase(self, phase, value):
        if isinstance(value, Exception):
            value, exception = None, value
            self.results.append(type(exception))
        else:
            exception = None
            self.results.append(value)
        self.pr.run_phase(phase, value, exception)
        if exception:
            raise exception

    def run(self, *values, seq=None):
        self._run_phase(self.phases.one, values[0])
        self._run_phase(self.phases.two, values[1])
        self._run_phase(self.phases.three, values[2])
        self._run_phase(self.phases.four, values[3])
        self.results.append(5)


def test_single():
    def handler_appender(ov, seq):
        seq.append("zero")
        yield ov.phases.one
        seq.append("one")
        yield ov.phases.two
        seq.append("two")
        yield ov.phases.three
        seq.append("three")
        yield ov.phases.four
        seq.append("four")

    ov = LightOverseer()
    ov.add(handler_appender)
    ov.run(1, 2, 3, 4)
    assert ov.results == ["zero", 1, "one", 2, "two", 3, "three", 4, "four", 5]
    assert not ov.errors


def test_dual():
    def handler_A(ov, seq):
        seq.append("A0")
        yield ov.phases.one
        seq.append("A1")
        yield ov.phases.two
        seq.append("A2")
        yield ov.phases.three
        seq.append("A3")
        yield ov.phases.four
        seq.append("A4")

    def handler_B(ov, seq):
        seq.append("B0")
        yield ov.phases.one
        seq.append("B1")
        yield ov.phases.two
        seq.append("B2")
        yield ov.phases.three
        seq.append("B3")
        yield ov.phases.four
        seq.append("B4")

    ov = LightOverseer()
    ov.add(handler_A)
    ov.add(handler_B)
    ov.run(1, 2, 3, 4)
    assert ov.results == [
        "A0",
        "B0",
        1,
        "A1",
        "B1",
        2,
        "A2",
        "B2",
        3,
        "A3",
        "B3",
        4,
        "A4",
        "B4",
        5,
    ]
    assert not ov.errors


def test_order():
    def handler_A(ov, seq):
        seq.append("A0")
        yield ov.phases.one
        seq.append("A1")
        yield ov.phases.two(priority=1)
        seq.append("A2")
        yield ov.phases.three(priority=-1)
        seq.append("A3")
        yield ov.phases.four
        seq.append("A4")

    def handler_B(ov, seq):
        seq.append("B0")
        yield ov.phases.one
        seq.append("B1")
        yield ov.phases.two(priority=2)
        seq.append("B2")
        yield ov.phases.three
        seq.append("B3")
        yield ov.phases.four(priority=1)
        seq.append("B4")

    ov = LightOverseer()
    ov.add(handler_A)
    ov.add(handler_B)
    ov.run(1, 2, 3, 4)
    assert ov.results == [
        "A0",
        "B0",
        1,
        "A1",
        "B1",
        2,
        "B2",
        "A2",
        3,
        "B3",
        "A3",
        4,
        "B4",
        "A4",
        5,
    ]
    assert not ov.errors


def test_partial_phases():
    def handler_A(ov, seq):
        seq.append("A0")
        yield ov.phases.two
        seq.append("A2")

    ov = LightOverseer()
    ov.add(handler_A)
    ov.run(1, 2, 3, 4)
    assert ov.results == ["A0", 1, 2, "A2", 3, 4, 5]
    assert not ov.errors


def test_add_multiple_copies():
    def handler_A(ov, seq):
        seq.append("A0")
        yield ov.phases.two
        seq.append("A2")

    ov = LightOverseer()
    # Even though we add it 3 times, we should only execute handler_A once
    ov.add(handler_A)
    ov.add(handler_A)
    ov.add(handler_A)
    ov.run(1, 2, 3, 4)
    assert ov.results == ["A0", 1, 2, "A2", 3, 4, 5]
    assert not ov.errors


def test_reenter():
    def handler_A(ov, seq):
        seq.append("A0")
        yield ov.phases.one
        seq.append("A1.1")
        yield ov.phases.one
        seq.append("A1.2")

    ov = LightOverseer()
    ov.add(handler_A)
    ov.run(1, 2, 3, 4)
    assert ov.results == ["A0", 1, "A1.1", "A1.2", 2, 3, 4, 5]
    assert not ov.errors


def test_sandwiched_order():
    def handler_A(ov, seq):
        yield ov.phases.two(priority=10)
        seq.append("A2.1")
        yield ov.phases.two(priority=5)
        seq.append("A2.2")
        yield ov.phases.two(priority=-10)
        seq.append("A2.3")

    def handler_B(ov, seq):
        yield ov.phases.two
        seq.append("B2.1")

    ov = LightOverseer()
    ov.add(handler_A)
    ov.add(handler_B)
    ov.run(1, 2, 3, 4)
    assert ov.results == [1, 2, "A2.1", "A2.2", "B2.1", "A2.3", 3, 4, 5]
    assert not ov.errors


def test_add_by_handler():
    def handler_A(ov, seq):
        seq.append("A0")
        yield ov.phases.one
        seq.append("A1")
        yield ov.phases.two(priority=1)
        seq.append("A2.1")
        ov.add(handler_B)
        seq.append("A2.2")
        yield ov.phases.three(priority=-1)
        seq.append("A3")
        yield ov.phases.four
        seq.append("A4")

    def handler_B(ov, seq):
        seq.append("B0")
        yield ov.phases.one
        seq.append("B1")
        yield ov.phases.two(priority=2)
        seq.append("B2")
        yield ov.phases.three
        seq.append("B3")
        yield ov.phases.four(priority=1)
        seq.append("B4")

    ov = LightOverseer()
    ov.add(handler_A)
    ov.run(1, 2, 3, 4)
    assert ov.results == [
        "A0",
        1,
        "A1",
        2,
        "A2.1",
        "B0",
        "B1",
        "A2.2",
        "B2",
        3,
        "B3",
        "A3",
        4,
        "B4",
        "A4",
        5,
    ]
    assert not ov.errors


def test_values():
    def handler_checker(ov, seq):
        one = yield ov.phases.one
        assert one == 1
        two = yield ov.phases.two
        assert two == 2
        three = yield ov.phases.three
        assert three == 3
        one_again = yield ov.phases.one
        assert one_again == 1
        four = yield ov.phases.four
        assert four == 4

    ov = LightOverseer()
    ov.add(handler_checker)
    ov.run(1, 2, 3, 4)
    assert not ov.errors


def test_done():
    def handler_checker(ov, seq):
        assert ov.phases.start.done

        yield ov.phases.one
        assert not ov.phases.one.done

        yield ov.phases.two
        assert ov.phases.one.done
        assert not ov.phases.two.done

        yield ov.phases.three
        assert ov.phases.two.done
        assert not ov.phases.three.done

        yield ov.phases.four
        assert ov.phases.three.done
        assert not ov.phases.four.done

    ov = LightOverseer()
    ov.add(handler_checker)
    ov.run(1, 2, 3, 4)
    assert not ov.errors


def test_running():
    def handler_checker(ov, seq):
        assert not ov.phases.start.running

        assert not ov.phases.one.running
        yield ov.phases.one
        assert ov.phases.one.running

        assert not ov.phases.two.running
        yield ov.phases.two
        assert ov.phases.two.running
        assert not ov.phases.one.running

        assert not ov.phases.three.running
        yield ov.phases.three
        assert ov.phases.three.running
        assert not ov.phases.two.running

        assert not ov.phases.four.running
        yield ov.phases.four
        assert ov.phases.four.running
        assert not ov.phases.three.running

    ov = LightOverseer()
    ov.add(handler_checker)
    ov.run(1, 2, 3, 4)
    assert not ov.errors


def test_runner_error():
    def handler_checker_1(ov, seq):
        try:
            yield ov.phases.two
        except TypeError:
            seq.append("error1")
            raise

    def handler_checker_2(ov, seq):
        try:
            yield ov.phases.two
        except TypeError:
            seq.append("error2")
            raise RuntimeError("unrelated")

    def handler_checker_3(ov, seq):
        try:
            yield ov.phases.two
        except TypeError:
            seq.append("error3")

    ov = LightOverseer()
    ov.add(handler_checker_1)
    ov.add(handler_checker_2)
    ov.add(handler_checker_3)
    with pytest.raises(TypeError):
        ov.run(1, TypeError("uh oh"), 3, 4)

    assert ov.results == [1, TypeError, "error1", "error2", "error3"]
    assert ov.errors == [RuntimeError]


def test_handler_error():
    def handler_A(ov, seq):
        yield ov.phases.two
        seq.append("A2")
        yield ov.phases.three
        seq.append("A3")

    def handler_E(ov, seq):
        yield ov.phases.two
        raise RuntimeError("boom")

    def handler_B(ov, seq):
        yield ov.phases.two
        seq.append("B2")
        yield ov.phases.three
        seq.append("B3")

    ov = LightOverseer()
    ov.add(handler_A)
    ov.add(handler_E)
    ov.add(handler_B)
    ov.run(1, 2, 3, 4)

    assert ov.results == [1, 2, "A2", "B2", 3, "A3", "B3", 4, 5]
    assert ov.errors == [RuntimeError]


def test_immediate_handler_error():
    def handler_E(ov, seq):
        raise RuntimeError("boom")

    ov = LightOverseer()
    ov.add(handler_E)
    ov.run(1, 2, 3, 4)

    assert ov.results == [1, 2, 3, 4, 5]
    assert ov.errors == [RuntimeError]


def test_not_a_generator():
    def handler_A(ov, seq):
        seq.append("A")

    ov = LightOverseer()
    ov.add(handler_A)
    ov.run(1, 2, 3, 4)

    assert ov.results == ["A", 1, 2, 3, 4, 5]
    assert not ov.errors


def test_bad_phase():
    def handler_A(ov, seq):
        yield ov.phases.one
        yield

    ov = LightOverseer()
    ov.add(handler_A)
    ov.run(1, 2, 3, 4)
    assert ov.errors == [Exception]

    with pytest.raises(Exception, match="must yield a valid phase"):
        raise ov.error_values[0]


def test_method():
    class Handler:
        def __init__(self, letter):
            self.letter = letter

        def __call__(self, ov, seq):
            seq.append(f"{self.letter}0")
            yield ov.phases.one
            seq.append(f"{self.letter}1")
            yield ov.phases.two
            seq.append(f"{self.letter}2")
            yield ov.phases.three
            seq.append(f"{self.letter}3")
            yield ov.phases.four
            seq.append(f"{self.letter}4")

    ov = LightOverseer()
    ov.add(Handler("A"))
    ov.add(Handler("B"))
    ov.run(1, 2, 3, 4)
    assert ov.results == [
        "A0",
        "B0",
        1,
        "A1",
        "B1",
        2,
        "A2",
        "B2",
        3,
        "A3",
        "B3",
        4,
        "A4",
        "B4",
        5,
    ]
    assert not ov.errors
