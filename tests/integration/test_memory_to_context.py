"""tests/integration/test_memory_to_context.py

场景 4: Memory → Context
验证链：冷记忆写入 → ColdIndex.search() 召回 → ContextAssembler Layer 3 拼接 → LLM 体现记忆。
"""
import pytest
from datetime import datetime

from src.storage import queries as q
from src.memory.cold_index import ColdIndex


@pytest.mark.llm
@pytest.mark.asyncio
async def test_cold_memory_recalled_and_affects_llm_reply(
    db, llm, context_asm, session_mgr, make_user,
):
    """用户提到 wtt → ColdIndex 召回记忆 → LLM 回复引用记忆。"""
    # 先创建用户（冷记忆依赖 users.notes 字段）
    await make_user(
        user_id="terminal-user", platform="terminal",
        relationship_type="trusted", interaction_count=20,
        last_interaction=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )

    # 写入 5 条关于 wtt 的冷记忆
    notes = [
        "wtt 喜欢喝冰美式咖啡",
        "上周和 wtt 一起去看了电影《流浪地球》",
        "wtt 最近在准备考研，压力很大",
        "wtt 的生日是 3 月 15 号",
        "wtt 说过她最喜欢的颜色是蓝色",
    ]
    for note in notes:
        await q.append_user_note(db, "terminal-user", note)

    # resolve 重新从 DB 读取 user → cold_notes 包含刚写入的内容
    session = await session_mgr.resolve("terminal-user", "terminal")
    user_message = "wtt 最近怎么样？她还喜欢喝什么吗？"
    prompt_ctx = await context_asm.assemble(session, user_message)

    # Layer 3 冷记忆应拼入 system_prompt
    assert "wtt" in prompt_ctx.system_prompt.lower()
    has_memory = any(
        keyword in prompt_ctx.system_prompt
        for keyword in ["冰美式", "咖啡", "流浪地球", "考研", "蓝色"]
    )
    assert has_memory, "Expected cold memory in system_prompt"

    # LLM 回复应体现记忆
    response = await llm.chat(prompt_ctx)
    reply_lower = response.reply_text.lower()
    memory_hints = ["冰美式", "咖啡", "电影", "流浪地球", "考研", "蓝色"]
    recalled = [h for h in memory_hints if h in reply_lower]
    assert len(recalled) > 0, (
        f"Expected LLM to reference memory. Reply: {response.reply_text[:200]}"
    )


@pytest.mark.asyncio
async def test_cold_index_search_finds_related_notes(db, make_user):
    """ColdIndex.search() 根据关键词正确召回关联笔记。"""
    # 创建用户并写入冷记忆
    await make_user(
        user_id="terminal-user", platform="terminal",
        relationship_type="trusted", interaction_count=20,
    )

    notes = [
        "wtt 喜欢喝冰美式咖啡",
        "上周和 wtt 一起去看了电影《流浪地球》",
        "wtt 最近在准备考研，压力很大",
        "wtt 的生日是 3 月 15 号",
        "wtt 说过她最喜欢的颜色是蓝色",
    ]
    for note in notes:
        await q.append_user_note(db, "terminal-user", note)

    # 从 DB 读取 notes 字段
    cursor = await db.execute(
        "SELECT notes FROM users WHERE user_id = ?", ("terminal-user",)
    )
    row = await cursor.fetchone()
    notes_text = row["notes"] if row and row["notes"] else ""

    # 构建索引并搜索
    index = ColdIndex()
    index.build(notes_text)

    results = index.search("wtt 咖啡")
    assert len(results) >= 1
    found = any("冰美式" in r or "咖啡" in r for r in results)
    assert found, "Should find coffee-related memory"
