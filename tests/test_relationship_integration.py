"""tests/test_relationship_integration.py — 关系状态机集成测试。不需要 API key。"""
import pytest
from src.relationship.familiarity import (
    compute_familiarity,
    compute_interaction_factor,
    compute_depth_ratio,
    compute_late_night_ratio,
    compute_initiative_ratio,
    build_layer4_context,
)
from src.relationship.branch_detector import (
    detect_branch_signals,
    update_streak,
    should_activate_branch,
    should_retreat_branch,
)
from src.storage.models import RelationshipType


def test_familiarity_full_trajectory():
    """验证从新用户到老用户熟悉度递增。"""
    f0 = compute_familiarity(0, 0, 0, 0)
    f1 = compute_familiarity(5, 1, 1, 1)
    f2 = compute_familiarity(25, 5, 5, 5)
    f3 = compute_familiarity(80, 16, 16, 16)

    assert f0 == 0.0
    assert f0 < f1 < f2 < f3  # 单调递增
    assert f3 >= 0.9  # 老用户应该很高


def test_familiarity_all_factors_contribute():
    """验证四个因子各自贡献。"""
    base = compute_familiarity(100, 0, 0, 0)
    with_depth = compute_familiarity(100, 20, 0, 0)
    with_late = compute_familiarity(100, 0, 25, 0)
    with_init = compute_familiarity(100, 0, 0, 33)

    assert with_depth > base
    assert with_late > base
    assert with_init > base


def test_branch_signals_do_not_cross_fire():
    """验证不同分支信号不会混淆。"""
    brother_result = detect_branch_signals(
        ["滚滚滚", "你他妈", "逆天", "抽象"], late_night_ratio=0.1, initiative_ratio=0.4,
    )
    assert brother_result == RelationshipType.BROTHER

    # 同一条消息不应该同时命中多个分支
    respected_result = detect_branch_signals(
        ["你还好吗", "你最近怎么样", "我觉得你可以"], late_night_ratio=0.1, initiative_ratio=0.2,
    )
    assert respected_result == RelationshipType.RESPECTED
    assert brother_result != respected_result


def test_streak_lifecycle():
    """模拟一个完整的分支切入→回退周期。"""
    # 模拟 streak 从 0 积累到 5
    streak = 0
    for i in range(6):
        streak = update_streak(streak, signal_match=True)
    assert streak == 6
    assert should_activate_branch(streak, current_branch=None) == True

    # 模拟已经分支后信号不匹配 → streak 归 -1
    streak = update_streak(streak, signal_match=False)
    assert streak == -1

    # 连续不匹配 → 回退
    for i in range(9):
        streak = update_streak(streak, signal_match=False)
    assert streak == -10
    assert should_retreat_branch(streak, current_branch=RelationshipType.BROTHER) == True


def test_build_layer4_all_relationship_types():
    """验证所有关系类型都能生成规则。"""
    for rel_type in RelationshipType:
        ctx = build_layer4_context(rel_type, familiarity=0.3)
        assert isinstance(ctx, str)
        assert len(ctx) > 20
        assert rel_type.value in ctx


def test_build_layer4_familiarity_changes_output():
    """验证熟悉度确实改变了输出。"""
    low = build_layer4_context(RelationshipType.TRUSTED, familiarity=0.2)
    high = build_layer4_context(RelationshipType.TRUSTED, familiarity=0.8)
    # 高低熟悉度输出应该不同
    assert low != high
