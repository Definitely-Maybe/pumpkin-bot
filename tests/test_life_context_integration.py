import pytest

from src.core.context import ContextAssembler
from src.core.contracts import UserSession
from src.persona.memory import SelfMemory
from src.storage.db import init_db
from src.storage.models import LifeEvent, PersonaState, RelationshipType, User
from src.storage import queries as q


def _write_persona_files(tmp_path):
    persona_path = tmp_path / "persona.md"
    self_path = tmp_path / "self.md"
    persona_path.write_text(
        "\n".join([
            "## Layer 0",
            "你是南瓜。",
            "## Layer 4",
            "关系规则。",
            "## Layer 5",
            "元认知。",
        ]),
        encoding="utf-8",
    )
    self_path.write_text("# self\n", encoding="utf-8")
    return persona_path, self_path


def _session(user: User, history=None):
    return UserSession(
        user=user,
        relationship=user.relationship_type,
        persona_state=PersonaState(),
        history=history or [],
    )


@pytest.mark.asyncio
async def test_context_assembler_injects_optional_life_context_when_natural(tmp_path):
    persona_path, self_path = _write_persona_files(tmp_path)
    conn = await init_db(tmp_path / "life-context.db")
    try:
        user = User(
            user_id="u1",
            platform="terminal",
            relationship_type=RelationshipType.TRUSTED,
            familiarity_score=0.8,
            interaction_count=80,
        )
        await q.insert_life_event(conn, LifeEvent(
            event_type="life",
            category="body_state",
            description="下午有点低电量，坐着放空了十分钟。",
        ))
        assembler = ContextAssembler(str(persona_path), SelfMemory(self_path), db=conn)

        ctx = await assembler.assemble(
            _session(user, history=[{"role": "user", "content": "你最近怎么样"}]),
            "今天好累，完全没电了",
        )

        assert "南瓜最近可联想到的一件生活小事" in ctx.system_prompt
        assert "下午有点低电量" in ctx.system_prompt
        assert "如果自然相关" in ctx.system_prompt
        assert "完全不要提" in ctx.system_prompt
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_context_assembler_omits_life_context_when_receptivity_is_low(tmp_path):
    persona_path, self_path = _write_persona_files(tmp_path)
    conn = await init_db(tmp_path / "life-context-low.db")
    try:
        user = User(
            user_id="u1",
            platform="terminal",
            relationship_type=RelationshipType.TRUSTED,
            familiarity_score=0.8,
            interaction_count=80,
        )
        await q.insert_life_event(conn, LifeEvent(
            event_type="life",
            category="body_state",
            description="下午有点低电量，坐着放空了十分钟。",
        ))
        assembler = ContextAssembler(str(persona_path), SelfMemory(self_path), db=conn)

        ctx = await assembler.assemble(
            _session(user, history=[{"role": "user", "content": "先说我的事"}]),
            "今天好累，完全没电了",
        )

        assert "南瓜最近可联想到的一件生活小事" not in ctx.system_prompt
        assert "下午有点低电量" not in ctx.system_prompt
    finally:
        await conn.close()
