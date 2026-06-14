"""tests/integration/test_relationship_to_context.py

场景 5: Relationship → Context
验证链：familiarity_score 计算 → LAYER4 规则动态插值 → LLM 语气随关系变化。
"""
import pytest
from datetime import datetime

from src.relationship.familiarity import compute_familiarity, build_layer4_context


@pytest.mark.llm
@pytest.mark.asyncio
async def test_stranger_vs_trusted_different_tone(
    db, llm, session_mgr, context_asm, make_user,
):
    """STRANGER 和 TRUSTED 对同一句话的回复风格不同。"""
    await make_user(
        user_id="stranger_001", platform="terminal",
        relationship_type="stranger", interaction_count=3,
        deep_topics_count=0, late_night_count=0, user_initiated_count=1,
        familiarity_score=0.05,
        last_interaction=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )
    await make_user(
        user_id="trusted_001", platform="terminal",
        relationship_type="trusted", interaction_count=80,
        deep_topics_count=12, late_night_count=8, user_initiated_count=30,
        familiarity_score=0.72,
        last_interaction=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )

    same_message = "今天心情不太好"

    session_s = await session_mgr.resolve("stranger_001", "terminal")
    ctx_s = await context_asm.assemble(session_s, same_message)
    resp_s = await llm.chat(ctx_s)

    session_t = await session_mgr.resolve("trusted_001", "terminal")
    ctx_t = await context_asm.assemble(session_t, same_message)
    resp_t = await llm.chat(ctx_t)

    # LAYER4 行为规则通过 build_layer4_context 生成，拼入 system_prompt
    assert "LAYER4" in ctx_s.system_prompt or "关系行为规则" in ctx_s.system_prompt
    assert "LAYER4" in ctx_t.system_prompt or "关系行为规则" in ctx_t.system_prompt

    assert resp_s.reply_text != resp_t.reply_text, (
        "Stranger and trusted should produce different replies"
    )

    print(f"\n--- STRANGER ---\n{resp_s.reply_text[:300]}")
    print(f"\n--- TRUSTED ---\n{resp_t.reply_text[:300]}")


@pytest.mark.asyncio
async def test_familiarity_calculator_stranger_vs_trusted():
    """验证 compute_familiarity 对 stranger 和 trusted 给出显著不同的分数。

    compute_familiarity 返回 0.0-1.0 范围。
    """
    score_s = compute_familiarity(
        interaction_count=3, deep_topics_count=0,
        user_initiated_count=1, late_night_count=0,
    )
    score_t = compute_familiarity(
        interaction_count=80, deep_topics_count=12,
        user_initiated_count=30, late_night_count=8,
    )

    assert score_s < 0.3, f"Stranger score should be low, got {score_s}"
    assert score_t > 0.5, f"Trusted score should be high, got {score_t}"
    assert score_t > score_s * 2, (
        f"Trusted ({score_t}) should be at least double stranger ({score_s})"
    )


def test_build_layer4_context_stranger_vs_trusted():
    """验证 build_layer4_context 为 stranger 和 trusted 生成不同的行为规则。"""
    from src.storage.models import RelationshipType

    low_familiarity = 0.1
    high_familiarity = 0.9

    ctx_stranger = build_layer4_context(RelationshipType.STRANGER, low_familiarity)
    ctx_trusted = build_layer4_context(RelationshipType.TRUSTED, high_familiarity)

    assert "stranger" in ctx_stranger.lower()
    assert "trusted" in ctx_trusted.lower()

    # 熟悉度低的 stranger 应该偏冷——保持距离
    assert "保持观察距离" in ctx_stranger or "礼貌" in ctx_stranger

    # 熟悉度高的 trusted 应该偏暖——放松、暴露
    assert "放松" in ctx_trusted or "暴露" in ctx_trusted or "袒露" in ctx_trusted

    # 不同类型/熟悉度产生的规则应该不同
    assert ctx_stranger != ctx_trusted, (
        "Stranger and trusted Layer4 rules should differ"
    )
