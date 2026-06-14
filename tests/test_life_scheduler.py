from datetime import datetime, timedelta

import pytest

from src.simulation.life_scheduler import LifeScheduler
from src.storage.db import init_db
from src.storage.models import LifeEvent
from src.storage import queries as q


@pytest.mark.asyncio
async def test_maybe_advance_creates_initial_event(tmp_path):
    conn = await init_db(tmp_path / "life-scheduler-initial.db")
    try:
        scheduler = LifeScheduler(conn)

        events = await scheduler.maybe_advance(now=datetime(2026, 6, 15, 12, 0, 0))

        assert len(events) == 1
        stored = await q.get_recent_life_events(conn, limit=5)
        assert len(stored) == 1
        assert stored[0]["event_type"] == "life"
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_maybe_advance_recent_event_returns_zero(tmp_path):
    conn = await init_db(tmp_path / "life-scheduler-cooldown.db")
    try:
        now = datetime(2026, 6, 15, 12, 0, 0)
        await q.insert_life_event(conn, LifeEvent(
            event_type="life",
            category="daily",
            description="刚刚发生过",
            created_at=(now - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S"),
        ))
        scheduler = LifeScheduler(conn)

        events = await scheduler.maybe_advance(now=now)

        assert events == []
        stored = await q.get_recent_life_events(conn, limit=5)
        assert len(stored) == 1
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_maybe_advance_catchup_caps_at_three(tmp_path):
    conn = await init_db(tmp_path / "life-scheduler-catchup.db")
    try:
        now = datetime(2026, 6, 15, 12, 0, 0)
        await q.insert_life_event(conn, LifeEvent(
            event_type="life",
            category="daily",
            description="很久以前",
            created_at=(now - timedelta(days=5)).strftime("%Y-%m-%d %H:%M:%S"),
        ))
        scheduler = LifeScheduler(conn)

        events = await scheduler.maybe_advance(now=now)

        assert len(events) == 3
        stored = await q.get_recent_life_events(conn, limit=10)
        assert len(stored) == 4
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_social_adapter_failure_does_not_block_life_generation(tmp_path):
    conn = await init_db(tmp_path / "life-scheduler-social-fail.db")
    try:
        now = datetime(2026, 6, 15, 12, 0, 0)
        await q.insert_life_event(conn, LifeEvent(
            event_type="life",
            category="daily",
            description="上一次生活事件",
            created_at=(now - timedelta(hours=7)).strftime("%Y-%m-%d %H:%M:%S"),
        ))

        class FailingAdapter:
            async def maybe_advance(self, user_message="", diagnostics=None):
                raise RuntimeError("social failed")

        scheduler = LifeScheduler(conn, social_adapter=FailingAdapter())

        events = await scheduler.maybe_advance(now=now, user_message="wtt 最近怎么样")

        assert len(events) == 1
        stored = await q.get_recent_life_events(conn, limit=10)
        assert len(stored) == 2
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_regular_life_advance_lets_social_scheduler_decide_without_name_mention(tmp_path):
    conn = await init_db(tmp_path / "life-scheduler-social-regular.db")
    try:
        now = datetime(2026, 6, 15, 12, 0, 0)
        await q.insert_life_event(conn, LifeEvent(
            event_type="life",
            category="daily",
            description="上一次生活事件",
            created_at=(now - timedelta(hours=7)).strftime("%Y-%m-%d %H:%M:%S"),
        ))

        class RecordingAdapter:
            def __init__(self):
                self.calls = []

            async def maybe_advance(self, user_message="", diagnostics=None):
                self.calls.append(user_message)
                return [{"event_id": 99, "event_type": "social", "description": "社交弧推进"}]

        adapter = RecordingAdapter()
        scheduler = LifeScheduler(conn, social_adapter=adapter)

        events = await scheduler.maybe_advance(now=now, user_message="今天随便聊聊")

        assert adapter.calls == ["今天随便聊聊"]
        assert any(event.get("event_type") == "social" for event in events)
    finally:
        await conn.close()
