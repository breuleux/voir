import threading

import pytest
from giving import give

from voir.phase import BaseOverseer, GivenOverseer, StopProgram


class LightOverseer(BaseOverseer):
    def __init__(self):
        self.results = []
        self.errors = []
        self.error_values = []
        super().__init__(
            ["one", "two", "three", "four"],
            args=[self, self.results],
            kwargs={},
        )

    def _on_instrument_error(self, err):
        if isinstance(err, AssertionError):
            self.stop(err)
        self.error_values.append(err)
        self.errors.append(type(err))

    def _run_phase(self, phase, value):
        with self.run_phase(phase) as set_value:
            if isinstance(value, Exception):
                self.results.append(type(value))
                raise value
            else:
                self.results.append(value)
                set_value(value)

    def _run(self, *values):
        self._run_phase(self.phases.one, values[0])
        self._run_phase(self.phases.two, values[1])
        self._run_phase(self.phases.three, values[2])
        self._run_phase(self.phases.four, values[3])
        self.results.append(5)


@pytest.fixture
def ov():
    return LightOverseer()


def test_single(ov):
    @ov.require
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

    ov(1, 2, 3, 4)
    assert not ov.errors
    assert ov.results == ["zero", 1, "one", 2, "two", 3, "three", 4, "four", 5]


def test_dual(ov):
    @ov.require
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

    @ov.require
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

    ov(1, 2, 3, 4)
    assert not ov.errors
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


def test_order(ov):
    @ov.require
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

    @ov.require
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

    ov(1, 2, 3, 4)
    assert not ov.errors
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


def test_partial_phases(ov):
    @ov.require
    def handler_A(ov, seq):
        seq.append("A0")
        yield ov.phases.two
        seq.append("A2")

    ov(1, 2, 3, 4)
    assert not ov.errors
    assert ov.results == ["A0", 1, 2, "A2", 3, 4, 5]


def test_add_multiple_copies(ov):
    def handler_A(ov, seq):
        seq.append("A0")
        yield ov.phases.two
        seq.append("A2")

    # Even though we add it 3 times, we should only execute handler_A once
    ov.require(handler_A)
    ov.require(handler_A)
    ov.require(handler_A)
    ov(1, 2, 3, 4)
    assert not ov.errors
    assert ov.results == ["A0", 1, 2, "A2", 3, 4, 5]


def test_reenter(ov):
    @ov.require
    def handler_A(ov, seq):
        seq.append("A0")
        yield ov.phases.one
        seq.append("A1.1")
        yield ov.phases.one
        seq.append("A1.2")

    ov(1, 2, 3, 4)
    assert not ov.errors
    assert ov.results == ["A0", 1, "A1.1", "A1.2", 2, 3, 4, 5]


def test_sandwiched_order(ov):
    @ov.require
    def handler_A(ov, seq):
        yield ov.phases.two(priority=10)
        seq.append("A2.1")
        yield ov.phases.two(priority=5)
        seq.append("A2.2")
        yield ov.phases.two(priority=-10)
        seq.append("A2.3")

    @ov.require
    def handler_B(ov, seq):
        yield ov.phases.two
        seq.append("B2.1")

    ov(1, 2, 3, 4)
    assert not ov.errors
    assert ov.results == [1, 2, "A2.1", "A2.2", "B2.1", "A2.3", 3, 4, 5]


def test_add_by_handler(ov):
    @ov.require
    def handler_A(ov, seq):
        seq.append("A0")
        yield ov.phases.one
        seq.append("A1")
        yield ov.phases.two(priority=1)
        seq.append("A2.1")
        hb = ov.require(handler_B)
        assert hb is handler_B
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

    ov(1, 2, 3, 4)
    assert not ov.errors
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


def test_values(ov):
    @ov.require
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

    ov(1, 2, 3, 4)
    assert not ov.errors


def test_done(ov):
    @ov.require
    def handler_checker(ov, seq):
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

    ov(1, 2, 3, 4)
    assert not ov.errors


def test_running(ov):
    @ov.require
    def handler_checker(ov, seq):
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

    ov(1, 2, 3, 4)
    assert not ov.errors


def test_runner_error(ov):
    @ov.require
    def handler_checker_1(ov, seq):
        try:
            yield ov.phases.two
        except TypeError:
            seq.append("error1")
            raise

    @ov.require
    def handler_checker_2(ov, seq):
        try:
            yield ov.phases.two
        except TypeError:
            seq.append("error2")
            raise RuntimeError("unrelated")

    @ov.require
    def handler_checker_3(ov, seq):
        try:
            yield ov.phases.two
        except TypeError:
            seq.append("error3")

    with pytest.raises(TypeError):
        ov(1, TypeError("uh oh"), 3, 4)

    assert ov.results == [1, TypeError, "error1", "error2", "error3"]
    assert ov.errors == [RuntimeError]


def test_handler_purposeful_error(ov):
    @ov.require
    def handler_A(ov, seq):
        yield ov.phases.two
        seq.append("A2")
        yield ov.phases.three
        seq.append("A3")

    @ov.require
    def handler_E(ov, seq):
        yield ov.phases.two
        ov.abort(RuntimeError("boom"))

    @ov.require
    def handler_B(ov, seq):
        yield ov.phases.two
        seq.append("B2")
        yield ov.phases.three
        seq.append("B3")

    with pytest.raises(RuntimeError):
        ov(1, 2, 3, 4)

    assert ov.results == [1, 2, "A2"]
    assert ov.errors == []


def test_immediate_handler_error(ov):
    @ov.require
    def handler_E(ov, seq):
        raise RuntimeError("boom")

    ov(1, 2, 3, 4)

    assert ov.results == [1, 2, 3, 4, 5]
    assert ov.errors == [RuntimeError]


def test_handler_not_a_generator(ov):
    @ov.require
    def handler_A(ov, seq):
        seq.append("A")

    ov(1, 2, 3, 4)

    assert not ov.errors
    assert ov.results == ["A", 1, 2, 3, 4, 5]


def test_bad_phase(ov):
    @ov.require
    def handler_A(ov, seq):
        yield ov.phases.one
        yield

    ov(1, 2, 3, 4)
    assert ov.errors == [Exception]

    with pytest.raises(Exception, match="must yield a valid phase"):
        raise ov.error_values[0]


def test_method(ov):
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

    ov.require(Handler("A"))
    ov.require(Handler("B"))
    ov(1, 2, 3, 4)
    assert not ov.errors
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


def test_state(ov):
    class Handler:
        def __init__(self, letter):
            self.__state__ = {"letter": letter}

        @property
        def letter(self):
            return self.__state__["letter"]

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

    @ov.require
    def handler_change(ov, seq):
        yield ov.phases.three
        h = ov.require(ha)
        assert h == {"letter": "A"}
        h["letter"] = "Z"

    ha = Handler("A")
    ov.require(ha)

    ov(1, 2, 3, 4)
    assert not ov.errors
    assert ov.results == [
        "A0",
        1,
        "A1",
        2,
        "A2",
        3,
        "Z3",
        4,
        "Z4",
        5,
    ]


def test_immediate(ov):
    @ov.require
    def handler_A(ov, seq):
        yield ov.phases.IMMEDIATE
        seq.append("A")

    ov(1, 2, 3, 4)
    assert not ov.errors
    assert ov.results == ["A", 1, 2, 3, 4, 5]


def test_immediate_cannot_have_priority(ov):
    @ov.require
    def handler_A(ov, seq):
        yield ov.phases.IMMEDIATE(priority=1000)
        seq.append("A")

    ov(1, 2, 3, 4)
    assert ov.errors == [TypeError]


def test_stop(ov):
    @ov.require
    def handler_A(ov, seq):
        yield ov.phases.two
        ov.stop()

    ov(1, 2, 3, 4)
    assert not ov.errors
    assert ov.results == [1, 2]
    assert ov.status == "stopped"


def test_stop_immediate(ov):
    def handler_A(ov, seq):
        ov.stop()

    ov.require(handler_A)
    ov(1, 2, 3, 4)
    assert not ov.errors
    assert ov.results == []
    assert ov.status == "stopped"


def test_stop_multiple_handlers(ov):
    @ov.require
    def handler_A(ov, seq):
        yield ov.phases.two
        ov.stop()

    @ov.require
    def handler_B(ov, seq):
        try:
            yield ov.phases.four
        except StopProgram:
            seq.append("B")

    @ov.require
    def handler_C(ov, seq):
        try:
            yield ov.phases.three
        except StopProgram:
            seq.append("C")
            raise RuntimeError("xxx")

    ov(1, 2, 3, 4)
    assert ov.errors == [RuntimeError]
    assert ov.results == [1, 2, "C", "B"]
    assert ov.status == "stopped"


def test_reenter_2(ov):
    @ov.require
    def handler_A(ov, seq):
        yield ov.phases.two
        ov(1, 2, 3, 4)  # error
        seq.append(111)

    ov(1, 2, 3, 4)
    assert ov.errors == [Exception]
    assert ov.results == [1, 2, 3, 4, 5]


def test_rerun(ov):
    ov(1, 2, 3, 4)
    with pytest.raises(Exception, match="Can only enter runner when"):
        ov(1, 2, 3, 4)


class LightGivenOverseer(GivenOverseer):
    def __init__(self):
        self.errors = []
        self.error_values = []
        super().__init__(
            ["one", "two", "three", "four"],
            args=[self],
            kwargs={},
        )

    def _run_phase(self, phase, value):
        with self.run_phase(phase) as set_value:
            if isinstance(value, Exception):
                self.give(error_type=type(value))
                raise value
            else:
                self.give(value=value)
                set_value(value)

    def _run(self, *values):
        self._run_phase(self.phases.one, values[0])
        self._run_phase(self.phases.two, values[1])
        self._run_phase(self.phases.three, values[2])
        self._run_phase(self.phases.four, values[3])
        self.give(value=5)


@pytest.fixture
def gov():
    return LightGivenOverseer()


def test_gov_give(gov):
    results = []

    @gov.require
    def handler_accumulator(ov):
        yield ov.phases.one
        ov.given["?value"].accum(results)

    @gov.require
    def handler_v(ov):
        yield ov.phases.two
        value = 13
        give(value)

    gov(1, 2, 3, 4)
    assert not gov.errors
    assert results == [2, 13, 3, 4, 5]


def test_gov_self_give(gov):
    results = []

    @gov.require
    def handler_accumulator(ov):
        yield ov.phases.one
        ov.given["?value"].accum(results)

    @gov.require
    def handler_v(ov):
        yield ov.phases.two
        value = 13
        ov.give(value=value)

    gov(1, 2, 3, 4)
    assert not gov.errors
    assert results == [2, 13, 3, 4, 5]


def test_gov_thread(gov):
    def q(ov):
        ov.give(value=4321)

    results = []

    @gov.require
    def handler_accumulator(ov):
        yield ov.phases.one
        ov.given["?value"].accum(results)

    @gov.require
    def handler_v(ov):
        thr = threading.Thread(target=q, args=(ov,))
        yield ov.phases.one
        thr.start()
        yield ov.phases.four
        thr.join()

    gov(1, 2, 3, 4)
    assert not gov.errors
    assert 4321 in results
