"""tests/test_emotional_index.py — 验证情感加权计算。"""

from src.memory.emotional_index import compute_weight


def test_deep_topic_weight_3():
    assert compute_weight(deep_topic=True, hour=15, msg_len=30, has_emoji=False) == 3


def test_late_night_weight_2():
    assert compute_weight(deep_topic=False, hour=23, msg_len=30, has_emoji=False) == 2


def test_long_form_weight_2():
    assert compute_weight(deep_topic=False, hour=15, msg_len=120, has_emoji=False) == 2


def test_emoji_weight_3():
    assert compute_weight(deep_topic=False, hour=15, msg_len=30, has_emoji=True) == 3


def test_default_weight_1():
    assert compute_weight(deep_topic=False, hour=15, msg_len=30, has_emoji=False) == 1


def test_highest_wins():
    # deep_topic + late_night + long_form → 3 (max)
    assert compute_weight(deep_topic=True, hour=23, msg_len=120, has_emoji=True) == 3
