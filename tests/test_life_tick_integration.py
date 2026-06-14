import pytest

from src.core.contracts import LLMResponse, UserSession
from src.core.postprocess import PostProcessor
from src.storage import queries as q
from src.storage.db import init_db
from src.storage.models import PersonaState, RelationshipType, User


@pytest.fixture
async def db(tmp_path):
    conn = await init_db(tmp_path / "life-tick.db")
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
async def test_life_tick_advances_scheduler_without_llm(db):
    class FakeLifeScheduler:
        def __init__(self):
            self.calls = []

        async def maybe_advance(self, user_message="", diagnostics=None):
            self.calls.append((user_message, diagnostics))
            if diagnostics is not None:
                diagnostics["life_due"] = True
            return [{"event_id": 1, "event_type": "life"}]

    user = User(user_id="life-user", platform="terminal")
    scheduler = FakeLifeScheduler()
    pp = PostProcessor(db, llm=None)
    pp._life_scheduler = scheduler

    await pp._life_tick(make_session(user), "今天普通聊聊")

    assert scheduler.calls
    assert scheduler.calls[0][0] == "今天普通聊聊"


@pytest.mark.asyncio
async def test_run_sidecars_calls_life_tick_instead_of_social_tick(db):
    class TrackingPostProcessor(PostProcessor):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.life_calls = 0
            self.social_calls = 0

        async def _life_tick(self, session, user_message):
            self.life_calls += 1

        async def _social_tick(self, session, user_message):
            self.social_calls += 1

    user = User(
        user_id="sidecar-life-user",
        platform="terminal",
        relationship_type=RelationshipType.STRANGER,
    )
    await q.upsert_user(db, user)
    pp = TrackingPostProcessor(db)

    await pp.run_sidecars(
        make_session(user),
        incoming_text="你好",
        response=LLMResponse(reply_text="你好呀", deep_topic=False, mood="neutral"),
        system_prompt="system",
    )

    assert pp.life_calls == 1
    assert pp.social_calls == 0
