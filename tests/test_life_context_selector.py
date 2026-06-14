from src.simulation.life_context_selector import LifeContextSelector
from src.storage.models import RelationshipType, User
from src.simulation.types import ReceptivityResult


def make_user(rel=RelationshipType.TRUSTED):
    return User(
        user_id="u1",
        platform="terminal",
        relationship_type=rel,
        familiarity_score=0.7,
        interaction_count=80,
    )


def test_selector_returns_none_when_no_events():
    selector = LifeContextSelector()

    result = selector.select(
        user=make_user(),
        user_message="今天好累",
        events=[],
        receptivity=ReceptivityResult(score=0.7, label="high"),
    )

    assert result is None


def test_selector_picks_related_body_state_event_for_tired_user():
    selector = LifeContextSelector()
    events = [
        {"event_id": 1, "event_type": "life", "category": "daily", "description": "上午去买水。", "shared_with_users": "[]"},
        {"event_id": 2, "event_type": "life", "category": "body_state", "description": "下午有点低电量，坐着放空了十分钟。", "shared_with_users": "[]"},
    ]

    result = selector.select(
        user=make_user(),
        user_message="今天好累，完全没电了",
        events=events,
        receptivity=ReceptivityResult(score=0.7, label="high"),
    )

    assert result is not None
    assert result.event_id == 2
    assert result.category == "body_state"


def test_selector_blocks_personal_event_for_stranger():
    selector = LifeContextSelector()
    events = [
        {"event_id": 2, "event_type": "life", "category": "reflection", "description": "深夜突然有点自我怀疑。", "shared_with_users": "[]"},
    ]

    result = selector.select(
        user=make_user(RelationshipType.STRANGER),
        user_message="你最近怎么样",
        events=events,
        receptivity=ReceptivityResult(score=0.8, label="high"),
    )

    assert result is None


def test_selector_blocks_when_user_is_in_strong_distress():
    selector = LifeContextSelector()
    events = [
        {"event_id": 2, "event_type": "life", "category": "body_state", "description": "下午低电量。", "shared_with_users": "[]"},
    ]

    result = selector.select(
        user=make_user(),
        user_message="我真的崩溃了，今天很难受，不知道怎么办",
        events=events,
        receptivity=ReceptivityResult(score=0.8, label="high"),
    )

    assert result is None


def test_selector_does_not_inject_daily_event_on_unrelated_message():
    selector = LifeContextSelector()
    events = [
        {"event_id": 3, "event_type": "life", "category": "daily", "description": "中午吃了个饭。", "shared_with_users": "[]"},
    ]

    result = selector.select(
        user=make_user(),
        user_message="这个作业我想换个写法",
        events=events,
        receptivity=ReceptivityResult(score=0.6, label="neutral"),
    )

    assert result is None


def test_format_prompt_context_uses_optional_language():
    selector = LifeContextSelector()
    candidate = selector.select(
        user=make_user(),
        user_message="今天好累",
        events=[
            {"event_id": 2, "event_type": "life", "category": "body_state", "description": "下午有点低电量。", "shared_with_users": "[]"},
        ],
        receptivity=ReceptivityResult(score=0.8, label="high"),
    )

    text = selector.format_for_prompt(candidate)

    assert "如果自然相关" in text
    assert "完全不要提" in text
    assert "不要解释这是记忆、事件或系统记录" in text
