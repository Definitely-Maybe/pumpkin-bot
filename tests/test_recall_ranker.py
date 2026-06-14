"""tests/test_recall_ranker.py"""
import pytest
from src.memory.recall_ranker import format_important_memories


def test_format_empty_memories():
    result = format_important_memories([])
    assert result == ""


def test_format_single_memory():
    memories = [
        {
            "message_id": 1,
            "direction": "incoming",
            "content": "我最近很焦虑工作的事",
            "weight": 3,
            "signals": ["deep_topic", "late_night"],
        }
    ]
    result = format_important_memories(memories)
    assert "对方" in result
    assert "焦虑" in result
    assert "deep_topic" in result


def test_format_multiple_memories():
    memories = [
        {"message_id": 1, "direction": "incoming", "content": "msg1", "weight": 3, "signals": ["deep_topic"]},
        {"message_id": 2, "direction": "outgoing", "content": "msg2", "weight": 2, "signals": []},
    ]
    result = format_important_memories(memories)
    assert "对方" in result
    assert "南瓜" in result
    assert "msg1" in result
    assert "msg2" in result


def test_content_truncation():
    long_content = "x" * 500
    memories = [
        {"message_id": 1, "direction": "incoming", "content": long_content, "weight": 1, "signals": []}
    ]
    result = format_important_memories(memories)
    # content should be truncated to 150 chars in output
    displayed = result.split("（")[0]
    assert len(displayed) < 300  # generous bound
