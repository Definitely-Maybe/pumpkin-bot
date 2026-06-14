"""tests/test_branch_detector.py"""
import pytest
from src.relationship.branch_detector import (
    BranchDetector,
    _score_signals,
    detect_branch_signals,
    is_boundary,
    update_streak,
    should_activate_branch,
    should_retreat_branch,
)
from src.storage.models import RelationshipType


# ─── _score_signals ────────────────────────────────────────────────

def test_score_signals_all_zero():
    scores = _score_signals(["今天天气真好", "吃了吗"])
    assert scores == {"roast": 0, "care": 0, "eager": 0}


def test_score_signals_mixed():
    scores = _score_signals(["滚滚滚", "你还好吗", "想你", "在干嘛", "睡不着"])
    assert scores["roast"] >= 1
    assert scores["care"] >= 1
    assert scores["eager"] >= 2


# ─── detect_branch_signals ─────────────────────────────────────────

def test_detect_signals_brother():
    messages = ["滚滚滚", "你他妈", "逆天"]
    result = detect_branch_signals(messages, late_night_ratio=0.3, initiative_ratio=0.4)
    assert result == RelationshipType.BROTHER


def test_detect_signals_respected():
    messages = ["你还好吗", "你最近怎么样", "你试试", "我觉得你可以"]
    result = detect_branch_signals(messages, late_night_ratio=0.1, initiative_ratio=0.2)
    assert result == RelationshipType.RESPECTED


def test_detect_signals_crush():
    messages = ["想你", "在干嘛", "睡不着", "陪我"]
    result = detect_branch_signals(messages, late_night_ratio=0.3, initiative_ratio=0.1)
    assert result is RelationshipType.CRUSH


def test_detect_signals_none():
    messages = ["今天天气真好", "吃了吗", "晚安"]
    result = detect_branch_signals(messages, late_night_ratio=0.1, initiative_ratio=0.1)
    assert result is None


# ─── is_boundary ───────────────────────────────────────────────────

def test_is_boundary_score_eq_2():
    # 某信号分 == 2（差 1 分触发）→ 边界
    messages = ["滚滚滚", "你他妈"]  # roast=2, 差 1 分
    assert is_boundary(messages, late_night_ratio=0.3, initiative_ratio=0.4) == True


def test_is_boundary_two_branches_active():
    # 两个分支同时 ≥2 → 边界
    messages = ["滚滚滚", "你他妈", "你还好吗", "你试试"]  # roast=2, care=2
    assert is_boundary(messages, late_night_ratio=0.3, initiative_ratio=0.4) == True


def test_is_boundary_signal_enough_but_aux_low():
    # eager≥3 但 late_night<0.2 → 边界
    messages = ["想你", "在干嘛", "睡不着", "陪我"]  # eager≥3
    assert is_boundary(messages, late_night_ratio=0.05, initiative_ratio=0.1) == True


def test_is_boundary_not_boundary():
    # 明确命中 → 不边界
    messages = ["滚滚滚", "你他妈", "逆天"]
    assert is_boundary(messages, late_night_ratio=0.3, initiative_ratio=0.4) == False


def test_is_boundary_nothing():
    messages = ["今天天气真好", "吃了吗", "晚安"]
    assert is_boundary(messages, late_night_ratio=0.1, initiative_ratio=0.1) == False


# ─── update_streak ─────────────────────────────────────────────────

def test_update_streak_positive():
    new_streak = update_streak(current_streak=3, signal_match=True)
    assert new_streak == 4


def test_update_streak_positive_capped():
    assert update_streak(current_streak=30, signal_match=True) == 30


def test_update_streak_first_miss():
    new_streak = update_streak(current_streak=5, signal_match=False)
    assert new_streak == -1


def test_update_streak_continued_miss():
    new_streak = update_streak(current_streak=-5, signal_match=False)
    assert new_streak == -6


def test_update_streak_negative_floor():
    assert update_streak(current_streak=-30, signal_match=False) == -30


# ─── should_activate / should_retreat ──────────────────────────────

def test_should_activate_branch():
    assert should_activate_branch(streak=5, current_branch=None) == True


def test_should_activate_branch_already_branched():
    assert should_activate_branch(streak=5, current_branch=RelationshipType.BROTHER) == False


def test_should_retreat_branch():
    assert should_retreat_branch(streak=-10, current_branch=RelationshipType.BROTHER) == True


def test_should_retreat_branch_not_branched():
    assert should_retreat_branch(streak=-10, current_branch=None) == False


def test_should_retreat_branch_not_enough():
    assert should_retreat_branch(streak=-5, current_branch=RelationshipType.CRUSH) == False


# ─── BranchDetector ────────────────────────────────────────────────

def test_detector_not_trusted_returns_none():
    detector = BranchDetector()
    result = detector.detect(
        recent_messages=[{"role": "user", "content": "滚滚滚"}] * 5,
        interaction_count=50,
        late_night_count=10,
        user_initiated_count=20,
        current_relationship=RelationshipType.ACQUAINTANCE,
    )
    assert result is None


def test_detector_insufficient_data_returns_none():
    detector = BranchDetector()
    result = detector.detect(
        recent_messages=[{"role": "user", "content": "滚滚滚"}] * 3,
        interaction_count=20,  # < 30
        late_night_count=10,
        user_initiated_count=20,
        current_relationship=RelationshipType.TRUSTED,
    )
    assert result is None


def test_detector_no_user_texts_returns_none():
    detector = BranchDetector()
    result = detector.detect(
        recent_messages=[{"role": "assistant", "content": "你好呀"}],
        interaction_count=50,
        late_night_count=10,
        user_initiated_count=20,
        current_relationship=RelationshipType.TRUSTED,
    )
    assert result is None


def test_detector_detects_brother():
    detector = BranchDetector()
    messages = [
        {"role": "user", "content": "滚滚滚"},
        {"role": "user", "content": "你他妈"},
        {"role": "user", "content": "逆天"},
    ]
    result = detector.detect(
        recent_messages=messages,
        interaction_count=50,
        late_night_count=15,
        user_initiated_count=20,
        current_relationship=RelationshipType.TRUSTED,
    )
    assert result == RelationshipType.BROTHER


@pytest.mark.asyncio
async def test_detector_with_fallback_rule_confident():
    """规则明确命中 → 不调 LLM，直接返回。"""
    detector = BranchDetector(llm=None)  # 无 LLM，确保走纯规则
    messages = [
        {"role": "user", "content": "滚滚滚"},
        {"role": "user", "content": "你他妈"},
        {"role": "user", "content": "逆天"},
    ]
    result = await detector.detect_with_fallback(
        recent_messages=messages,
        interaction_count=50,
        late_night_count=15,
        user_initiated_count=20,
        current_relationship=RelationshipType.TRUSTED,
    )
    assert result == RelationshipType.BROTHER


@pytest.mark.asyncio
async def test_detector_with_fallback_boundary_no_llm():
    """边界 case 但无 LLM → 回退到规则结果（可能为 None）。"""
    detector = BranchDetector(llm=None)
    messages = [
        {"role": "user", "content": "滚滚滚"},
        {"role": "user", "content": "你他妈"},
    ]  # roast=2 → 边界
    result = await detector.detect_with_fallback(
        recent_messages=messages,
        interaction_count=50,
        late_night_count=15,
        user_initiated_count=20,
        current_relationship=RelationshipType.TRUSTED,
    )
    # 无 LLM 时回退到规则结果（规则判定为 None，因为只有 2 个信号词）
    assert result is None


@pytest.mark.asyncio
async def test_detector_with_fallback_converts_llm_result_to_relationship_type():
    """LLM 兜底返回字符串时，检测器应保持 RelationshipType 契约。"""

    class FakeLLM:
        async def classify_branch(self, user_texts, system_prompt):
            return "crush"

    detector = BranchDetector(llm=FakeLLM())
    result = await detector.detect_with_fallback(
        recent_messages=[
            {"role": "user", "content": "想你"},
            {"role": "user", "content": "在干嘛"},
        ],
        interaction_count=50,
        late_night_count=15,
        user_initiated_count=20,
        current_relationship=RelationshipType.TRUSTED,
    )

    assert result is RelationshipType.CRUSH


@pytest.mark.asyncio
async def test_detector_with_fallback_not_trusted():
    """非 trusted 阶段 → 直接返回 None，不调 LLM。"""
    detector = BranchDetector(llm=None)
    result = await detector.detect_with_fallback(
        recent_messages=[{"role": "user", "content": "滚滚滚"}] * 5,
        interaction_count=50,
        late_night_count=15,
        user_initiated_count=20,
        current_relationship=RelationshipType.ACQUAINTANCE,
    )
    assert result is None
