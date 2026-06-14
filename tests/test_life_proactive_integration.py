import json
from datetime import datetime

import pytest

from src.core.contracts import UserSession
from src.core.postprocess import PostProcessor
from src.storage import queries as q
from src.storage.db import init_db
from src.storage.models import LifeEvent, PersonaState, RelationshipType, TriggerType, User


@pytest.fixture
async def db(tmp_path):
    conn = await init_db(tmp_path / "life-proactive.db")
    try:
        yield conn
    finally:
        await conn.close()


def make_session(user: User, history=None) -> UserSession:
    return UserSession(
        user=user,
        relationship=user.relationship_type,
        persona_state=PersonaState(),
        history=history or [],
    )


async def _trusted_user(db, user_id="u1") -> User:
    user = User(
        user_id=user_id,
        platform="terminal",
        relationship_type=RelationshipType.TRUSTED,
        familiarity_score=0.8,
        interaction_count=81,
        deep_topics_count=10,
        user_initiated_count=20,
        last_interaction=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )
    await q.upsert_user(db, user)
    existing_task_id = await q.enqueue_proactive(
        db, user.user_id, TriggerType.MEMORY_TRIGGER, "今天已经有一条非生活主动消息",
    )
    await q.mark_proactive_sent(db, existing_task_id)
    return user


class FakeLLM:
    def __init__(self):
        self.calls = []

    async def generate_proactive(
        self, user_name, trigger_type, context, system_prompt, relationship_type,
    ):
        self.calls.append({
            "trigger_type": trigger_type,
            "context": context,
            "relationship_type": relationship_type,
        })
        return "我刚才有点低电量，缓了一会儿。"


@pytest.mark.asyncio
async def test_life_proactive_uses_policy_event_and_marks_shared_after_send(db):
    user = await _trusted_user(db)
    event = await q.insert_life_event(db, LifeEvent(
        event_type="life",
        category="body_state",
        description="下午有点低电量，坐着放空了十分钟。",
    ))
    llm = FakeLLM()

    sent = []

    async def proactive_sender(user_id, messages):
        sent.append((user_id, messages))
        return True

    pp = PostProcessor(db, llm=llm, proactive_sender=proactive_sender)
    await pp._check_proactive_triggers(
        make_session(
            user,
            history=[{"role": "user", "content": "你最近怎么样"}],
        ),
        system_prompt="system",
        user_message="普通聊天。",
    )

    refreshed = await q.get_latest_life_event(db)
    shared = json.loads(refreshed["shared_with_users"])

    assert sent == [(user.user_id, ["我刚才有点低电量，缓了一会儿。"])]
    assert llm.calls[0]["trigger_type"] == TriggerType.LIFE_STORY.value
    assert "下午有点低电量" in llm.calls[0]["context"]
    assert "如果不自然就不要提" in llm.calls[0]["context"]
    assert user.user_id in shared
    assert refreshed["event_id"] == event.event_id


@pytest.mark.asyncio
async def test_life_proactive_does_not_share_low_value_daily_event(db):
    user = await _trusted_user(db)
    await q.insert_life_event(db, LifeEvent(
        event_type="life",
        category="daily",
        description="吃了个饭。",
    ))
    llm = FakeLLM()

    pp = PostProcessor(db, llm=llm)
    await pp._check_proactive_triggers(
        make_session(user),
        system_prompt="system",
        user_message="普通聊天。",
    )

    latest = await q.get_latest_life_event(db)

    assert llm.calls == []
    assert json.loads(latest["shared_with_users"]) == []
