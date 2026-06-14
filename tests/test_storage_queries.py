"""Regression tests for storage query helpers."""

from datetime import datetime, timedelta

import pytest

from src.storage import queries as q
from src.storage.db import init_db
from src.storage.models import LifeEvent, TriggerType, User


@pytest.mark.asyncio
async def test_upsert_user_updates_topics_and_shared_jokes_on_conflict(tmp_path):
    conn = await init_db(tmp_path / "storage.db")
    try:
        user = User(user_id="u1", platform="terminal")
        await q.upsert_user(conn, user)

        user.topics_discussed = '["面试"]'
        user.shared_jokes = '["梗"]'
        await q.upsert_user(conn, user)

        refreshed = await q.get_user(conn, user.user_id)
        assert refreshed.topics_discussed == '["面试"]'
        assert refreshed.shared_jokes == '["梗"]'
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_get_latest_life_event_returns_newest(tmp_path):
    conn = await init_db(tmp_path / "life-latest.db")
    try:
        older = (datetime.now() - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
        newer = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        await q.insert_life_event(conn, LifeEvent(
            event_type="life",
            category="daily",
            description="早一点的事",
            created_at=older,
        ))
        await q.insert_life_event(conn, LifeEvent(
            event_type="life",
            category="body_state",
            description="新的事",
            created_at=newer,
        ))

        latest = await q.get_latest_life_event(conn)

        assert latest is not None
        assert latest["description"] == "新的事"
        assert latest["category"] == "body_state"
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_get_recent_life_events_for_user_filters_shared(tmp_path):
    conn = await init_db(tmp_path / "life-unshared.db")
    try:
        shared = await q.insert_life_event(conn, LifeEvent(
            event_type="life",
            category="daily",
            description="已经讲过的事",
        ))
        await q.mark_event_shared(conn, shared.event_id, "u1")
        await q.insert_life_event(conn, LifeEvent(
            event_type="life",
            category="daily",
            description="还没讲过的事",
        ))

        events = await q.get_recent_life_events_for_user(conn, "u1", limit=10, unshared_only=True)

        assert [e["description"] for e in events] == ["还没讲过的事"]
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_count_proactive_today_by_types(tmp_path):
    conn = await init_db(tmp_path / "proactive-types.db")
    try:
        await q.upsert_user(conn, User(user_id="u1", platform="terminal"))
        await q.enqueue_proactive(conn, "u1", TriggerType.LIFE_STORY, "生活分享")
        task_id = await q.enqueue_proactive(conn, "u1", TriggerType.MEMORY_TRIGGER, "追问")
        await q.mark_proactive_sent(conn, 1)
        await q.mark_proactive_sent(conn, task_id)

        life_count = await q.count_proactive_today_by_types(
            conn,
            "u1",
            [TriggerType.LIFE_STORY, TriggerType.SOCIAL_SHARE],
        )

        assert life_count == 1
    finally:
        await conn.close()
