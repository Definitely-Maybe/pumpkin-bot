"""tests/integration/test_social_to_evolution.py

场景 1: Social → Evolution
验证链：社交弧推进 → EvolutionEngine 检测 → Reflector 反思 → WriteBack 写回。
"""
import json
import pytest
from datetime import datetime, timedelta

from src.storage.models import Direction, ArcStatus, SocialArc, SocialCharacter
from src.storage import queries as q
from src.evolution.engine import EvolutionEngine
from src.persona.memory import SelfMemory


@pytest.mark.llm
@pytest.mark.asyncio
async def test_social_arc_aftermath_triggers_evolution(
    db, llm, persona_path, self_md_path, make_user, insert_message,
):
    """社交弧高潮结束 → EvolutionEngine 检测 → 执行反思。"""

    # ─── Setup ──────────────────────────────────────
    await make_user(
        user_id="terminal-user", platform="terminal",
        relationship_type="trusted", interaction_count=60,
        deep_topics_count=8, late_night_count=5,
        user_initiated_count=15,
    )

    now = datetime.now()
    for i in range(25):
        await insert_message(
            user_id="terminal-user",
            direction=Direction.INCOMING if i % 2 == 0 else Direction.OUTGOING,
            content=f"测试对话第{i}轮",
            deep_topic=(i % 5 == 0),
            created_at=(now - timedelta(hours=i)).strftime("%Y-%m-%d %H:%M:%S"),
        )

    char = SocialCharacter(
        character_id="char_wtt",
        name="wtt",
        source="self_md",
        traits='["温柔","细腻"]',
        core_tension="表达与压抑",
        relationship_to_nan_gua="朋友",
        allowed_arc_types='["friendship","romance"]',
    )
    await q.upsert_character(db, char)

    arc = SocialArc(
        arc_id="arc_test_001",
        character_id="char_wtt",
        arc_type="romance",
        status=ArcStatus.AFTERMATH,
        trigger_source="time",
        event_count=4,
        max_events=4,
        started_at=(now - timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S"),
    )
    await q.insert_arc(db, arc)

    await q.insert_summary(db, "terminal-user",
        "[最近3天] 和wtt深夜聊天，话题涉及感情和未来", 0, 60)

    cursor = await db.execute("SELECT message_id FROM messages LIMIT 5")
    mids = []
    async for row in cursor:
        mids.append(row["message_id"])
    for mid in mids[:3]:
        await q.insert_emotional_peak(db, "terminal-user", message_id=mid, weight=3,
                                      signals=["deep_topic", "late_night"])

    cursor = await db.execute("SELECT COUNT(*) as cnt FROM evolution_log")
    row = await cursor.fetchone()
    assert row["cnt"] == 0

    # ─── Execute ────────────────────────────────────
    engine = EvolutionEngine(
        db, llm,
        self_memory=SelfMemory(self_md_path),
        persona_path=persona_path,
        self_md_path=self_md_path,
        config={"evolution": {"reflection": {"day_of_week": 6, "hour": 23}}},
    )
    result = await engine.maybe_reflect()

    # ─── Verify ─────────────────────────────────────
    assert result is True
    cursor = await db.execute("SELECT COUNT(*) as cnt FROM evolution_log")
    row = await cursor.fetchone()
    assert row["cnt"] >= 1

    cursor = await db.execute(
        "SELECT findings FROM evolution_log ORDER BY created_at DESC LIMIT 1"
    )
    row = await cursor.fetchone()
    findings = json.loads(row["findings"])
    assert isinstance(findings, dict)


@pytest.mark.llm
@pytest.mark.asyncio
async def test_reflector_input_includes_social_events():
    """验证 Reflector.assemble_input 正确包含社交事件。"""
    from src.evolution.reflector import Reflector

    social_events = [
        {"description": "wtt 和南瓜深夜聊天，讨论了未来的打算"},
        {"description": "ccx 进入了恋爱弧的 RISING 阶段"},
    ]
    input_text = Reflector.assemble_input(
        summaries=[{"summary_text": "本周和wtt聊了很多"}],
        recent_corrections=[{"description": "用户说我不够直接"}],
        recent_social_events=social_events,
        emotional_peaks=[{"signals": "deep_topic", "weight": 3}],
        deep_ratio_change=0.35,
        late_night_ratio_change=0.15,
        self_md_sections="wtt: 朋友关系",
        persona_baseline="你是南瓜。",
    )
    assert "wtt" in input_text
    assert "ccx" in input_text
    assert len(input_text) > 200
