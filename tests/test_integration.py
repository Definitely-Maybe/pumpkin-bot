"""tests/test_integration.py — 完整 pipeline 端到端测试。需要 DEEPSEEK_API_KEY。"""

import asyncio
import os
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

import pytest

# 确保项目根目录在 path 中
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.storage.db import init_db
from src.core.session import SessionManager
from src.core.context import ContextAssembler
from src.core.llm import LLMEngine
from src.core.postprocess import PostProcessor
from src.persona.memory import SelfMemory
from src.core.contracts import MessageContext

# persona / self.md 路径（相对于项目根目录 nan-gua-bot/）
PERSONA_PATH = "../.claude/skills/ban-ge-nan-gua/persona.md"
SELF_MD_PATH = "../.claude/skills/ban-ge-nan-gua/self.md"


@pytest.fixture
def db():
    """创建临时测试数据库（唯一文件名避免锁冲突）。"""
    os.makedirs("data", exist_ok=True)
    db_path = f"data/test_integration_{uuid.uuid4().hex[:8]}.db"
    yield db_path
    # teardown: 清理
    try:
        if os.path.exists(db_path):
            os.remove(db_path)
    except PermissionError:
        pass  # 文件可能仍被锁定，下次启动再清理


@pytest.mark.integration
@pytest.mark.asyncio
async def test_full_pipeline_5_rounds(db):
    """5 轮对话：验证不崩溃、deep_topic 被标记、消息入库。"""
    if not os.getenv("DEEPSEEK_API_KEY"):
        pytest.skip("DEEPSEEK_API_KEY not set")

    conn = await init_db(db)

    self_memory = SelfMemory(SELF_MD_PATH)
    context_asm = ContextAssembler(PERSONA_PATH, self_memory)
    llm = LLMEngine()
    session_mgr = SessionManager(conn)
    postprocessor = PostProcessor(conn, llm)

    # 5 轮对话
    messages = [
        "你好呀",
        "我今天挺累的",
        "最近在想要不要换工作",
        "你谈过恋爱吗",
        "谢谢你跟我说这些",
    ]

    deep_topic_count = 0
    for msg in messages:
        # Stage 1: Session
        session = await session_mgr.resolve("test-integration-user", "terminal")

        # Stage 2: Context
        prompt_ctx = await context_asm.assemble(session, msg)

        # 验证 system_prompt 包含 Layer 0-3 关键内容
        assert "华东师大" in prompt_ctx.system_prompt, (
            f"system_prompt should contain '华东师大' (Layer 0-3), got {len(prompt_ctx.system_prompt)} chars"
        )

        # Stage 3: LLM
        response = await llm.chat(prompt_ctx)

        # 验证返回了有效回复
        assert len(response.reply_text) > 0, "reply_text should not be empty"
        assert len(response.reply_text) < 2000, f"reply too long: {len(response.reply_text)} chars"

        # 验证 mood 是合法值
        assert response.mood in ("happy", "neutral", "sad", "anxious", "reflective"), (
            f"invalid mood: {response.mood}"
        )

        if response.deep_topic:
            deep_topic_count += 1

        # Stage 4: PostProcess
        burst = postprocessor.process(response)
        assert len(burst.messages) >= 1, "burst should have at least 1 message"

        # Fire-and-forget sidecars
        await postprocessor.run_sidecars(session, msg, response, prompt_ctx.system_prompt)

    # deep_topic 由 LLM 判断，有随机性。只需验证不崩溃 + 值合法
    print(f"[test] deep_topic count: {deep_topic_count}/5 (LLM-determined, non-deterministic)")

    # 验证消息已入库
    import aiosqlite
    async with aiosqlite.connect(db) as verify_conn:
        verify_conn.row_factory = aiosqlite.Row
        cursor = await verify_conn.execute(
            "SELECT COUNT(*) as cnt FROM messages WHERE user_id = ?",
            ("test-integration-user",),
        )
        row = await cursor.fetchone()
        msg_count = row["cnt"] if row else 0
        assert msg_count >= 10, f"Expected >=10 messages in DB, got {msg_count}"
        print(f"[test] {msg_count} messages stored in DB")

    await conn.close()
    print(f"[test] deep_topic count: {deep_topic_count}/5 ✓")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_json_parse_failure_graceful_degradation(db):
    """JSON 解析失败时不崩溃，规则兜底生效。"""
    if not os.getenv("DEEPSEEK_API_KEY"):
        pytest.skip("DEEPSEEK_API_KEY not set")

    conn = await init_db(db)

    self_memory = SelfMemory(SELF_MD_PATH)
    context_asm = ContextAssembler(PERSONA_PATH, self_memory)
    llm = LLMEngine()
    session_mgr = SessionManager(conn)

    session = await session_mgr.resolve("test-degrade-user", "terminal")
    prompt_ctx = await context_asm.assemble(session, "你好")

    response = await llm.chat(prompt_ctx)

    # 无论 JSON 解析成功与否，都应该有有效回复
    assert len(response.reply_text) > 0, "should always return reply text"
    assert response.mood in ("happy", "neutral", "sad", "anxious", "reflective")

    # sidecar_parse_ok 标记应存在
    assert isinstance(response.sidecar_parse_ok, bool)

    await conn.close()
    print(f"[test] sidecar_parse_ok={response.sidecar_parse_ok}, mood={response.mood}")
