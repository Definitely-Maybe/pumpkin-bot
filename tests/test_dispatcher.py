"""tests/test_dispatcher.py"""
import pytest
from src.proactive.dispatcher import Dispatcher, TerminalDispatcher


def test_dispatcher_is_abstract():
    with pytest.raises(TypeError):
        Dispatcher()  # ABC 不能直接实例化


def test_terminal_dispatcher_instantiable():
    td = TerminalDispatcher()
    assert td is not None
    assert hasattr(td, 'send')
    assert hasattr(td, 'flush_pending')


def test_terminal_dispatcher_has_db_attr_default_none():
    td = TerminalDispatcher()
    assert td.db is None
