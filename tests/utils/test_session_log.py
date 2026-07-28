from __future__ import annotations

import logging

from phoenixadult.utils.logging.session_log import SessionLogHandler


def _handler(capacity: int = 200) -> SessionLogHandler:
    handler = SessionLogHandler(capacity=capacity)
    handler.setFormatter(logging.Formatter('%(message)s'))
    return handler


def _log(handler: SessionLogHandler, message: str) -> None:
    handler.emit(logging.LogRecord('phoenixadult', logging.INFO, __file__, 1, message, None, None))


def test_an_empty_buffer_reports_nothing() -> None:
    seq, lines, reset = _handler().tail()
    assert (seq, lines, reset) == (0, [], True)


def test_tail_returns_the_whole_session_then_only_what_is_new() -> None:
    handler = _handler()
    _log(handler, 'first')
    _log(handler, 'second')

    seq, lines, reset = handler.tail()
    assert lines == ['first', 'second'] and reset is True and seq == 2

    _log(handler, 'third')
    seq, lines, reset = handler.tail(seq)
    assert lines == ['third'] and reset is False and seq == 3

    assert handler.tail(seq) == (3, [], False)


def test_a_caller_that_fell_behind_gets_a_full_replacement() -> None:
    handler = _handler(capacity=3)
    for i in range(6):
        _log(handler, f'line {i}')

    seq, lines, reset = handler.tail(1)

    assert reset is True
    assert lines == ['line 3', 'line 4', 'line 5']
    assert seq == 6


def test_the_buffer_keeps_only_the_newest_lines() -> None:
    handler = _handler(capacity=4)
    for i in range(10):
        _log(handler, f'line {i}')

    _seq, lines, _reset = handler.tail()

    assert lines == ['line 6', 'line 7', 'line 8', 'line 9']


def test_a_multi_line_record_counts_as_one_line_each() -> None:
    handler = _handler()
    _log(handler, 'traceback:\n  frame one\n  frame two')

    seq, lines, _reset = handler.tail()

    assert lines == ['traceback:', '  frame one', '  frame two']
    assert seq == 3


def test_a_formatter_failure_never_raises_into_the_caller() -> None:
    handler = _handler()
    handler.setFormatter(logging.Formatter('%(nope)s'))
    handler.handleError = lambda record: None  # type: ignore[method-assign]

    _log(handler, 'ignored')

    assert handler.tail() == (0, [], True)
