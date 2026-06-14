"""tests/test_loop_detector.py"""
import pytest
from src.memory.loop_detector import LoopDetector


def test_detect_by_rules_interview():
    detector = LoopDetector()
    result = detector.detect_by_rules("我下周有个字节的面试")
    assert result is not None
    assert result["method"] == "rules"
    assert "面试" in result["description"]
    assert result["follow_up_window"] == "next_week"


def test_detect_by_rules_hospital():
    detector = LoopDetector()
    result = detector.detect_by_rules("明天去医院做体检")
    assert result is not None
    assert result["follow_up_window"] == "tomorrow"


def test_detect_by_rules_no_match():
    detector = LoopDetector()
    result = detector.detect_by_rules("今天天气真好")
    assert result is None


def test_detect_by_rules_meeting():
    detector = LoopDetector()
    result = detector.detect_by_rules("周末约饭吗")
    assert result is not None
    assert result["follow_up_window"] == "in_3_days"


def test_detect_by_rules_deadline():
    detector = LoopDetector()
    result = detector.detect_by_rules("下周五要答辩了")
    assert result is not None
    assert result["follow_up_window"] == "next_week"


def test_loop_detector_init_without_llm():
    detector = LoopDetector()  # no llm, no db
    assert detector.llm is None
    assert detector.db is None


def test_loop_detector_init_with_db():
    detector = LoopDetector(db="mock_db")
    assert detector.db == "mock_db"
