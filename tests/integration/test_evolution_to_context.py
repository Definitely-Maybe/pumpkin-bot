"""tests/integration/test_evolution_to_context.py

场景 6: Evolution → Context
验证链：EvolutionEngine 反思 → WriteBack 更新 persona.md → ContextAssembler 读到新人格 → LLM 变化。

⚠️ 此测试会修改真实 persona.md 和 self.md 文件。setup 备份，teardown 恢复。
"""
import datetime
import shutil
from pathlib import Path

import pytest

from src.evolution.writeback import WriteBack


@pytest.fixture
def backup_persona(persona_path):
    """备份 persona.md，teardown 无条件恢复。"""
    backup_path = Path(persona_path).with_suffix(".md.backup")
    shutil.copy2(persona_path, backup_path)
    yield backup_path
    # teardown: restore original and clean up backup
    shutil.copy2(backup_path, persona_path)
    backup_path.unlink(missing_ok=True)


@pytest.fixture
def backup_self_md(self_md_path):
    """备份 self.md，teardown 无条件恢复。"""
    backup_path = Path(self_md_path).with_suffix(".md.backup")
    shutil.copy2(self_md_path, backup_path)
    yield backup_path
    # teardown: restore original and clean up backup
    shutil.copy2(backup_path, self_md_path)
    backup_path.unlink(missing_ok=True)


@pytest.mark.llm
@pytest.mark.asyncio
async def test_evolution_changes_persona_affects_llm_behavior(
    db, llm, context_asm, session_mgr, make_user,
    persona_path, self_md_path,
    backup_persona, backup_self_md,
):
    """人格进化后 LLM 回复风格改变。"""

    # ─── Phase 1: 进化前 baseline ─────────────────────
    await make_user(
        user_id="terminal-user", platform="terminal",
        relationship_type="trusted", interaction_count=50,
        last_interaction=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )

    session = await session_mgr.resolve("terminal-user", "terminal")
    ctx_before = await context_asm.assemble(session, "你觉得你是一个什么样的人？")
    resp_before = await llm.chat(ctx_before)

    # ─── Phase 2: 模拟进化 ────────────────────────────
    evolution_result = {
        "self_insights": [{
            "trigger": "跨模块测试",
            "old_view": "我性格比较含蓄",
            "new_view": "我变得更直接了，说话不绕弯",
            "confidence": 0.9,
        }],
        "persona_changes": [{
            "target_layer": "1",
            "rule_type": "add",
            "new_text": "- 测试标记：当被问到自我认知时，直接说'我现在更直接了'",
            "reason": "测试进化闭环",
        }],
        "growth_note": "进化测试：变得更直接",
    }

    versions_dir = str(Path(persona_path).parent / "versions")

    WriteBack.snapshot(persona_path, versions_dir, datetime.datetime.now().strftime("%Y-%m-%d"))
    WriteBack.snapshot(self_md_path, versions_dir, datetime.datetime.now().strftime("%Y-%m-%d"))
    WriteBack.append_changelog(versions_dir, evolution_result, "测试进化触发")
    WriteBack.append_self_md(self_md_path, evolution_result, versions_dir)
    WriteBack.apply_persona_delta(persona_path, evolution_result["persona_changes"], versions_dir)

    # ─── Phase 3: 进化后验证 ──────────────────────────
    from src.persona.memory import SelfMemory
    from src.core.context import ContextAssembler as CtxAsm
    fresh_self = SelfMemory(self_md_path)
    fresh_ctx = CtxAsm(persona_path, fresh_self, db)

    session2 = await session_mgr.resolve("terminal-user", "terminal")
    ctx_after = await fresh_ctx.assemble(session2, "你觉得你是一个什么样的人？")
    resp_after = await llm.chat(ctx_after)

    # ─── Verify ───────────────────────────────────────
    persona_content = Path(persona_path).read_text(encoding="utf-8")
    assert "测试标记" in persona_content or "更直接" in persona_content or "不绕弯" in persona_content, \
        "persona.md should contain the new rule"

    assert resp_before.reply_text != resp_after.reply_text, \
        "Evolution should produce a different reply"

    print(f"\n=== BEFORE ===\n{resp_before.reply_text[:300]}")
    print(f"\n=== AFTER ===\n{resp_after.reply_text[:300]}")
