"""Regression tests for storage query helpers."""

import pytest

from src.storage import queries as q
from src.storage.db import init_db
from src.storage.models import User


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
