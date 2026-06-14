"""tests/test_familiarity.py"""
import math
from src.relationship.familiarity import (
    compute_interaction_factor,
    compute_depth_ratio,
    compute_late_night_ratio,
    compute_initiative_ratio,
    compute_familiarity,
    build_layer4_context,
)
from src.storage.models import RelationshipType


def test_interaction_factor_zero():
    assert compute_interaction_factor(0) == 0.0


def test_interaction_factor_fifty():
    f = compute_interaction_factor(50)
    assert 0.95 <= f <= 1.0


def test_interaction_factor_hundred():
    assert compute_interaction_factor(100) >= 0.98


def test_depth_ratio_zero():
    assert compute_depth_ratio(deep_topics=0, total=50) == 0.0


def test_depth_ratio_high():
    assert compute_depth_ratio(deep_topics=20, total=100) >= 0.95


def test_late_night_ratio():
    assert compute_late_night_ratio(late_night=25, total=100) >= 0.95


def test_initiative_ratio():
    assert compute_initiative_ratio(initiated=33, total=100) >= 0.95


def test_compute_familiarity_new_user():
    f = compute_familiarity(
        interaction_count=0, deep_topics_count=0,
        late_night_count=0, user_initiated_count=0,
    )
    assert f == 0.0


def test_compute_familiarity_veteran():
    f = compute_familiarity(
        interaction_count=100, deep_topics_count=20,
        late_night_count=25, user_initiated_count=33,
    )
    assert 0.8 <= f <= 1.0


def test_compute_familiarity_capped_at_one():
    f = compute_familiarity(
        interaction_count=10000, deep_topics_count=5000,
        late_night_count=5000, user_initiated_count=5000,
    )
    assert f <= 1.0


def test_build_layer4_context_stranger_low_familiarity():
    ctx = build_layer4_context(RelationshipType.STRANGER, familiarity=0.1)
    assert "礼貌" in ctx or "观察" in ctx


def test_build_layer4_context_brother_high_familiarity():
    ctx = build_layer4_context(RelationshipType.BROTHER, familiarity=0.9)
    assert "放松" in ctx or "滚滚滚" in ctx or "兄弟" in ctx.lower()


def test_build_layer4_context_returns_string():
    ctx = build_layer4_context(RelationshipType.TRUSTED, familiarity=0.5)
    assert isinstance(ctx, str)
    assert len(ctx) > 20
