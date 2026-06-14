"""tests/test_debug.py"""
import io
import sys
import pytest
from src.utils.debug import DebugLogger


class TestDebugLogger:
    def test_level_0_suppresses_all(self):
        buf = io.StringIO()
        dl = DebugLogger(level=0, target=buf)
        dl.turn_start("u1", "terminal", "hi", "2024-01-01 00:00")
        dl.sidecar(1, "✅", "测试", "详情")
        dl.turn_end(1.5)
        assert buf.getvalue() == ""

    def test_level_1_shows_sidecar_not_stage(self):
        buf = io.StringIO()
        dl = DebugLogger(level=1, target=buf)
        dl.turn_start("u1", "terminal", "hi", "2024-01-01 00:00")
        dl.session(0.72, "trusted", 147, 3, "brother")
        dl.sidecar(1, "✅", "测试", "详情")
        output = buf.getvalue()
        assert "测试" in output
        assert "详情" in output
        assert "trusted" not in output  # session is stage-level

    def test_level_2_shows_everything(self):
        buf = io.StringIO()
        dl = DebugLogger(level=2, target=buf)
        dl.turn_start("u1", "terminal", "hi", "2024-01-01 00:00")
        dl.session(0.72, "trusted", 147, 3, "brother")
        dl.sidecar(1, "✅", "测试", "详情")
        output = buf.getvalue()
        assert "terminal" in output
        assert "trusted" in output
        assert "测试" in output

    def test_stderr_is_default_target(self):
        dl = DebugLogger(level=2)
        assert dl._out is sys.stderr

    def test_turn_counter_increments(self):
        buf = io.StringIO()
        dl = DebugLogger(level=2, target=buf)
        dl.turn_start("u1", "terminal", "hi", "2024-01-01 00:00")
        dl.turn_end(1.0)
        dl.turn_start("u1", "terminal", "hi2", "2024-01-01 00:01")
        output = buf.getvalue()
        assert "第 1 轮" in output
        assert "第 2 轮" in output

    def test_llm_output_shows_model_and_timing(self):
        buf = io.StringIO()
        dl = DebugLogger(level=2, target=buf)
        dl.llm("deepseek-chat", 1.3, 312, 89)
        output = buf.getvalue()
        assert "deepseek-chat" in output
        assert "1.3s" in output or "1.30s" in output
        assert "312" in output
        assert "89" in output
