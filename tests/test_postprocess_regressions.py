"""Regression tests for postprocess side-effect wiring."""

import pytest

from src.core.contracts import LLMResponse, UserSession
from src.core.postprocess import PostProcessor
from src.storage import queries as q
from src.storage.db import init_db
from src.storage.models import (
    Direction,
    Message,
    PersonaState,
    RelationshipType,
    TriggerType,
    User,
)


@pytest.fixture
async def db(tmp_path):
    conn = await init_db(tmp_path / "postprocess.db")
    try:
        yield conn
    finally:
        await conn.close()


def make_session(user: User) -> UserSession:
    return UserSession(
        user=user,
        relationship=user.relationship_type,
        persona_state=PersonaState(),
    )


@pytest.mark.asyncio
async def test_branch_drift_activates_branch_after_consistent_detected_direction(db):
    user = User(
        user_id="branch-user",
        platform="terminal",
        relationship_type=RelationshipType.TRUSTED,
        interaction_count=50,
        late_night_count=15,
        user_initiated_count=20,
    )
    await q.upsert_user(db, user)
    for text in ("滚滚滚", "你他妈", "逆天"):
        await q.insert_message(db, Message(
            user_id=user.user_id,
            direction=Direction.INCOMING,
            content=text,
        ))

    pp = PostProcessor(db)

    for _ in range(5):
        refreshed = await q.get_user(db, user.user_id)
        await pp._check_branch_drift(make_session(refreshed), system_prompt="")

    refreshed = await q.get_user(db, user.user_id)
    assert refreshed.relationship_type == RelationshipType.BROTHER
    assert refreshed.branch_type == RelationshipType.BROTHER.value
    assert refreshed.branch_signal_streak == 0


@pytest.mark.asyncio
async def test_branch_drift_keeps_active_branch_when_signals_still_match(db):
    user = User(
        user_id="active-branch-user",
        platform="terminal",
        relationship_type=RelationshipType.BROTHER,
        branch_type=RelationshipType.BROTHER.value,
        interaction_count=50,
        late_night_count=15,
        user_initiated_count=20,
    )
    await q.upsert_user(db, user)
    for text in ("滚滚滚", "你他妈", "逆天"):
        await q.insert_message(db, Message(
            user_id=user.user_id,
            direction=Direction.INCOMING,
            content=text,
        ))

    pp = PostProcessor(db)

    for _ in range(10):
        refreshed = await q.get_user(db, user.user_id)
        await pp._check_branch_drift(make_session(refreshed), system_prompt="")

    refreshed = await q.get_user(db, user.user_id)
    assert refreshed.relationship_type == RelationshipType.BROTHER
    assert refreshed.branch_type == RelationshipType.BROTHER.value
    assert refreshed.branch_signal_streak > 0


@pytest.mark.asyncio
async def test_summary_checkpoint_uses_message_id_not_interaction_count(db):
    class FakeSummaryWriter:
        async def generate(self, system_prompt, history, user_display_name):
            return "聊到了情绪和未来。"

    user = User(
        user_id="summary-user",
        platform="terminal",
        interaction_count=24,
    )
    await q.upsert_user(db, user)
    for i in range(48):
        await q.insert_message(db, Message(
            user_id=user.user_id,
            direction=Direction.INCOMING,
            content=f"history {i}",
        ))

    pp = PostProcessor(db, summary_writer=FakeSummaryWriter())
    await pp.run_sidecars(
        make_session(user),
        incoming_text="触发摘要",
        response=LLMResponse(reply_text="回复", deep_topic=False, mood="neutral"),
        system_prompt="system",
    )

    cursor = await db.execute(
        "SELECT message_range_end FROM summaries WHERE user_id = ?",
        (user.user_id,),
    )
    summary = await cursor.fetchone()
    cursor = await db.execute(
        "SELECT MAX(message_id) AS max_id FROM messages WHERE user_id = ?",
        (user.user_id,),
    )
    max_row = await cursor.fetchone()

    assert summary["message_range_end"] == max_row["max_id"]


@pytest.mark.asyncio
async def test_proactive_trigger_sends_via_runtime_sender_and_marks_sent(db):
    class FakeLLM:
        async def generate_proactive(
            self, user_name, trigger_type, context, system_prompt, relationship_type,
        ):
            return "我想起你之前说的事了"

    sent = []

    async def proactive_sender(user_id, messages):
        sent.append((user_id, messages))
        return True

    user = User(
        user_id="proactive-user",
        platform="terminal",
        relationship_type=RelationshipType.TRUSTED,
        interaction_count=80,
        deep_topics_count=10,
        user_initiated_count=20,
    )
    await q.upsert_user(db, user)
    await q.insert_open_loop(db, user.user_id, "用户有个待追问事项")
    existing_task_id = await q.enqueue_proactive(
        db, user.user_id, TriggerType.MILESTONE, "今天已经发过",
    )
    await q.mark_proactive_sent(db, existing_task_id)

    pp = PostProcessor(db, llm=FakeLLM(), proactive_sender=proactive_sender)
    await pp._check_proactive_triggers(make_session(user), system_prompt="system")

    cursor = await db.execute(
        "SELECT trigger_type, proposed_message, status FROM proactive_queue WHERE user_id = ?",
        (user.user_id,),
    )
    rows = await cursor.fetchall()
    generated = [
        row for row in rows
        if row["proposed_message"] == "我想起你之前说的事了"
    ]

    assert sent == [(user.user_id, ["我想起你之前说的事了"])]
    assert len(generated) == 1
    assert generated[0]["trigger_type"] == TriggerType.MEMORY_TRIGGER.value
    assert generated[0]["status"] == "sent"
