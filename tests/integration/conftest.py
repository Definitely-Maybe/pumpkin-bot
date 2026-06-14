"""tests/integration/conftest.py — 跨模块集成测试共享 fixtures。"""
import os
import sys
from pathlib import Path

import pytest
import aiosqlite

# 确保项目根目录在 sys.path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.storage.db import init_db
from src.core.llm import LLMEngine
from src.persona.memory import SelfMemory
from src.core.context import ContextAssembler
from src.core.session import SessionManager
from src.core.postprocess import PostProcessor
from src.memory.summary_writer import SummaryWriter
from src.memory.loop_detector import LoopDetector


@pytest.fixture
async def db(tmp_path):
    """创建临时 SQLite 数据库，teardown 自动删除。"""
    db_path = tmp_path / "test_cross.db"
    conn = await init_db(str(db_path))
    yield conn
    await conn.close()


@pytest.fixture
def llm():
    """真实 LLMEngine（从环境变量读取 API key）。"""
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        pytest.skip("DEEPSEEK_API_KEY not set")
    return LLMEngine(
        model=os.getenv("LLM_MODEL", "deepseek-chat"),
        max_tokens=1024,
        temperature=0.7,
    )


@pytest.fixture
def project_root():
    """项目根目录路径。"""
    return Path(__file__).parent.parent.parent


@pytest.fixture
def persona_path(project_root):
    """persona.md 真实路径。"""
    p = project_root / "data" / "persona.md"
    if not p.exists():
        pytest.skip("persona.md not found")
    return str(p)


@pytest.fixture
def self_md_path(project_root):
    """self.md 真实路径。"""
    p = project_root / "data" / "self.md"
    if not p.exists():
        pytest.skip("self.md not found")
    return str(p)


@pytest.fixture
def real_config(persona_path, self_md_path, tmp_path):
    """最小可用的 config dict。"""
    return {
        "storage": {"db_path": str(tmp_path / "test.db")},
        "llm": {"model": "deepseek-chat", "max_tokens": 1024, "temperature": 0.7},
        "persona": {
            "persona_md_path": persona_path,
            "self_md_path": self_md_path,
        },
        "platforms": {"terminal": {"enabled": True}, "wechat": {"enabled": False}},
    }


@pytest.fixture
def self_memory(self_md_path):
    """SelfMemory 实例。"""
    return SelfMemory(self_md_path)


@pytest.fixture
def context_asm(persona_path, self_memory, db):
    """ContextAssembler 实例。"""
    return ContextAssembler(persona_path, self_memory, db)


@pytest.fixture
def session_mgr(db):
    """SessionManager 实例。"""
    return SessionManager(db)


@pytest.fixture
def summary_writer(llm):
    """SummaryWriter 实例。"""
    return SummaryWriter(llm)


@pytest.fixture
def loop_detector(llm, db):
    """LoopDetector 实例。"""
    return LoopDetector(llm, db)


@pytest.fixture
def postprocessor(db, llm, summary_writer, loop_detector, persona_path, self_md_path):
    """PostProcessor 实例。"""
    return PostProcessor(
        db, llm,
        summary_writer=summary_writer,
        loop_detector=loop_detector,
        persona_path=persona_path,
        self_md_path=self_md_path,
        config={},
    )


@pytest.fixture
def make_user(db):
    """Helper：创建用户并写入 users 表。"""
    from src.storage.models import User
    from src.storage import queries as q

    async def _make(user_id="terminal-user", platform="terminal",
                    relationship_type="trusted", interaction_count=50,
                    deep_topics_count=5, late_night_count=3,
                    user_initiated_count=10,
                    **kwargs):
        from src.storage.models import RelationshipType as RT
        if isinstance(relationship_type, str):
            relationship_type = RT(relationship_type)
        user = User(
            user_id=user_id,
            platform=platform,
            relationship_type=relationship_type,
            interaction_count=interaction_count,
            deep_topics_count=deep_topics_count,
            late_night_count=late_night_count,
            user_initiated_count=user_initiated_count,
            **kwargs,
        )
        await q.upsert_user(db, user)
        return user
    return _make


@pytest.fixture
def insert_message(db):
    """Helper：插入一条消息。"""
    from src.storage.models import Message, Direction
    from src.storage import queries as q

    async def _insert(user_id="terminal-user", direction=Direction.INCOMING,
                      content="测试消息", deep_topic=False,
                      created_at=None):
        return await q.insert_message(db, Message(
            user_id=user_id,
            direction=direction,
            content=content,
            deep_topic=deep_topic,
            created_at=created_at,
        ))
    return _insert
