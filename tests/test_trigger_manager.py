"""tests/test_trigger_manager.py"""
from datetime import datetime, timedelta
from src.proactive.trigger_manager import TriggerManager
from src.storage.models import (
    RelationshipType, User, TriggerType,
)


def make_user(relationship, interaction_count=50,
              deep=10, initiated=15, late=10,
              last_interaction=None):
    """快速构造测试用 User。"""
    return User(
        user_id="test-u1",
        platform="terminal",
        relationship_type=relationship,
        familiarity_score=0.5,
        interaction_count=interaction_count,
        deep_topics_count=deep,
        user_initiated_count=initiated,
        late_night_count=late,
        last_interaction=last_interaction,
    )


# ─── inactivity ──────────────────────────────────────────────

def test_inactivity_skip_stranger():
    user = make_user(RelationshipType.STRANGER, last_interaction="2020-01-01 00:00:00")
    assert TriggerManager._check_inactivity(user) is False


def test_inactivity_trusted_3_days():
    three_days_ago = (datetime.now() - timedelta(days=3, hours=1)).strftime("%Y-%m-%d %H:%M:%S")
    user = make_user(RelationshipType.TRUSTED, last_interaction=three_days_ago)
    result = TriggerManager._check_inactivity(user)
    assert result is True


def test_inactivity_trusted_recently_active():
    one_hour_ago = (datetime.now() - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
    user = make_user(RelationshipType.TRUSTED, last_interaction=one_hour_ago)
    assert TriggerManager._check_inactivity(user) is False


# ─── milestone ───────────────────────────────────────────────

def test_milestone_hit_100():
    user = make_user(RelationshipType.TRUSTED, interaction_count=100)
    result = TriggerManager._check_milestone(user)
    assert result == "100"


def test_milestone_miss_101():
    user = make_user(RelationshipType.TRUSTED, interaction_count=101)
    assert TriggerManager._check_milestone(user) is None


def test_milestone_hit_50():
    user = make_user(RelationshipType.ACQUAINTANCE, interaction_count=50)
    assert TriggerManager._check_milestone(user) == "50"


# ─── time_of_day ─────────────────────────────────────────────

def test_time_of_day_not_night():
    assert TriggerManager._check_time_of_day(is_late_night=False, already_sent_today=False) is False


def test_time_of_day_late_night_not_sent():
    assert TriggerManager._check_time_of_day(is_late_night=True, already_sent_today=False) is True


def test_time_of_day_late_night_already_sent():
    assert TriggerManager._check_time_of_day(is_late_night=True, already_sent_today=True) is False


# ─── memory_trigger ──────────────────────────────────────────

def test_memory_trigger_no_open_loops():
    assert TriggerManager._check_memory_trigger(open_loops=[]) is False


def test_memory_trigger_has_open_loop():
    loops = [{"description": "面试", "follow_up_window": "next_week"}]
    result = TriggerManager._check_memory_trigger(open_loops=loops)
    assert result is True


# ─── social / life ───────────────────────────────────────────

def test_social_share_no_events():
    assert TriggerManager._check_social_share(unshared_events=[]) is False


def test_social_share_has_social_event():
    events = [{"event_type": "social", "category": "daily", "description": "吵架了"}]
    assert TriggerManager._check_social_share(unshared_events=events) is True


def test_social_share_filters_night_reflection():
    events = [{"event_type": "social", "category": "night_reflection", "description": "深夜反思"}]
    assert TriggerManager._check_social_share(unshared_events=events) is False


def test_life_story_no_events():
    assert TriggerManager._check_life_story(unshared_events=[]) is False


def test_life_story_has_daily_event():
    events = [{"event_type": "reflection", "category": "daily", "description": "看到猫"}]
    assert TriggerManager._check_life_story(unshared_events=events) is True


# ─── relation gate ────────────────────────────────────────────

def test_relation_gate_stranger_cant_memory():
    assert TriggerManager._is_allowed(TriggerType.MEMORY_TRIGGER, RelationshipType.STRANGER) is False


def test_relation_gate_stranger_can_milestone():
    assert TriggerManager._is_allowed(TriggerType.MILESTONE, RelationshipType.STRANGER) is True


def test_relation_gate_trusted_all():
    for t in TriggerType:
        assert TriggerManager._is_allowed(t, RelationshipType.TRUSTED) is True
