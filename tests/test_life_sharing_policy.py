from src.simulation.life_sharing_policy import LifeSharingPolicy
from src.simulation.types import ReceptivityResult, ShareLevel
from src.storage.models import RelationshipType, TriggerType, User


def make_user(rel=RelationshipType.TRUSTED, familiarity=0.8):
    return User(
        user_id="u1",
        platform="terminal",
        relationship_type=rel,
        familiarity_score=familiarity,
        interaction_count=80,
    )


def event(
    event_id=1,
    category="daily",
    description="出门吹了会儿风。",
    event_type="life",
    shared_with_users="[]",
):
    return {
        "event_id": event_id,
        "event_type": event_type,
        "category": category,
        "description": description,
        "shared_with_users": shared_with_users,
    }


def high_receptivity():
    return ReceptivityResult(score=0.85, label="high")


def test_default_does_not_share_low_value_daily_event():
    decision = LifeSharingPolicy().select_event(
        user=make_user(RelationshipType.TRUSTED),
        user_message="普通聊天，没什么特别的。",
        events=[event()],
        receptivity=ReceptivityResult(score=0.6, label="neutral"),
        life_shares_today=0,
    )

    assert decision.should_share is False
    assert decision.event is None
    assert decision.reason == "no_event_scored_high_enough"


def test_blocks_when_user_is_in_strong_distress():
    decision = LifeSharingPolicy().select_event(
        user=make_user(RelationshipType.CRUSH),
        user_message="我真的崩溃了，不知道怎么办，撑不住了。",
        events=[event(category="body_state", description="下午有点低电量，坐着放空了十分钟。")],
        receptivity=high_receptivity(),
        life_shares_today=0,
    )

    assert decision.should_share is False
    assert decision.reason == "user_distress"


def test_blocks_low_receptivity_and_daily_limit():
    policy = LifeSharingPolicy()

    low = policy.select_event(
        user=make_user(RelationshipType.TRUSTED),
        user_message="普通聊天。",
        events=[event(category="body_state", description="下午有点低电量。")],
        receptivity=ReceptivityResult(score=0.2, label="low"),
        life_shares_today=0,
    )
    limited = policy.select_event(
        user=make_user(RelationshipType.TRUSTED),
        user_message="普通聊天。",
        events=[event(category="body_state", description="下午有点低电量。")],
        receptivity=high_receptivity(),
        life_shares_today=1,
    )

    assert low.should_share is False
    assert low.reason == "low_receptivity"
    assert limited.should_share is False
    assert limited.reason == "daily_limit_reached"


def test_ignores_event_already_shared_with_user():
    decision = LifeSharingPolicy().select_event(
        user=make_user(RelationshipType.TRUSTED),
        user_message="普通聊天。",
        events=[
            event(
                category="body_state",
                description="下午有点低电量，坐着放空了十分钟。",
                shared_with_users='["u1"]',
            )
        ],
        receptivity=high_receptivity(),
        life_shares_today=0,
    )

    assert decision.should_share is False
    assert decision.reason == "no_shareable_events"


def test_private_and_creative_events_are_conservative_for_strangers():
    policy = LifeSharingPolicy()

    private_decision = policy.select_event(
        user=make_user(RelationshipType.STRANGER, familiarity=0.1),
        user_message="你今天做了什么？",
        events=[event(category="reflection", description="深夜突然有点自我怀疑。")],
        receptivity=high_receptivity(),
        life_shares_today=0,
    )
    creative_decision = policy.select_event(
        user=make_user(RelationshipType.STRANGER, familiarity=0.1),
        user_message="你今天做了什么？",
        events=[event(category="creative", description="卡在 bot 的一个 prompt 上。")],
        receptivity=high_receptivity(),
        life_shares_today=0,
    )

    assert private_decision.should_share is False
    assert private_decision.reason == "no_shareable_events"
    assert creative_decision.should_share is False
    assert creative_decision.reason == "no_shareable_events"


def test_explicit_ask_allows_public_status_share_for_stranger():
    decision = LifeSharingPolicy().select_event(
        user=make_user(RelationshipType.STRANGER, familiarity=0.1),
        user_message="南瓜你今天做了什么？最近怎么样？",
        events=[event(category="daily", description="下午出门买水，顺手晒了会儿太阳。")],
        receptivity=ReceptivityResult(score=0.5, label="neutral"),
        life_shares_today=0,
    )

    assert decision.should_share is True
    assert decision.event["event_id"] == 1
    assert decision.reason == "explicit_user_ask"
    assert decision.share_level == ShareLevel.PUBLIC
    assert decision.trigger_type == TriggerType.LIFE_STORY
    assert "如果不自然就不要提" in decision.instruction
    assert "不要变成南瓜独白" in decision.instruction


def test_trusted_selects_high_value_event_for_proactive_share():
    events = [
        event(event_id=1, category="daily", description="吃了个饭。"),
        event(event_id=2, category="body_state", description="下午有点低电量，坐着放空了十分钟。"),
    ]

    decision = LifeSharingPolicy().select_event(
        user=make_user(RelationshipType.TRUSTED),
        user_message="普通聊天。",
        events=events,
        receptivity=high_receptivity(),
        life_shares_today=0,
    )

    assert decision.should_share is True
    assert decision.event["event_id"] == 2
    assert decision.reason == "proactive_high_value_event"
    assert decision.trigger_type == TriggerType.LIFE_STORY
    assert "下午有点低电量" in decision.instruction
