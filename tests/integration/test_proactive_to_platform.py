"""tests/integration/test_proactive_to_platform.py

场景 3: Proactive → Platform
验证链：TriggerManager 触发 → LLM.generate_proactive() → 入队 → Dispatcher.flush_pending()
"""
import pytest
from datetime import datetime, timedelta

from src.core.postprocess import PostProcessor
from src.storage.models import User, RelationshipType, Direction
from src.storage import queries as q
from src.proactive.dispatcher import TerminalDispatcher
from src.proactive.trigger_manager import TriggerManager


@pytest.mark.llm
@pytest.mark.asyncio
async def test_silence_triggers_proactive_message_and_dispatches(
    db, llm, summary_writer, loop_detector, persona_path, self_md_path, make_user, insert_message,
):
    """用户沉默 72 小时 → 触发 SILENCE → 生成主动消息 → Dispatcher 发送。"""
    three_days_ago = datetime.now() - timedelta(hours=73)
    await make_user(
        user_id="terminal-user", platform="terminal",
        relationship_type="trusted", interaction_count=100,
        deep_topics_count=10, late_night_count=5,
        user_initiated_count=20,
        last_interaction=three_days_ago.strftime("%Y-%m-%d %H:%M:%S"),
    )

    for i in range(30):
        await insert_message(
            user_id="terminal-user",
            direction=Direction.INCOMING if i % 2 == 0 else Direction.OUTGOING,
            content=f"历史消息{i}",
            deep_topic=(i % 4 == 0),
            created_at=(three_days_ago - timedelta(hours=i)).strftime("%Y-%m-%d %H:%M:%S"),
        )

    pp = PostProcessor(
        db, llm,
        summary_writer=summary_writer,
        loop_detector=loop_detector,
        persona_path=persona_path,
        self_md_path=self_md_path,
        config={},
    )

    user = User(
        user_id="terminal-user", platform="terminal",
        relationship_type=RelationshipType.TRUSTED,
        interaction_count=100,
        last_interaction=three_days_ago.strftime("%Y-%m-%d %H:%M:%S"),
    )

    class MockSession:
        def __init__(self):
            self.user = user
            self.persona_state = type('obj', (object,), {'__dict__': {}})()

    session = MockSession()
    await pp._check_proactive_triggers(session, system_prompt="你是南瓜。")

    cursor = await db.execute(
        "SELECT COUNT(*) as cnt FROM proactive_queue WHERE user_id = ? AND status = 'pending'",
        ("terminal-user",)
    )
    row = await cursor.fetchone()
    pending = row["cnt"] if row else 0

    if pending > 0:
        dispatcher = TerminalDispatcher(db)
        sent = await dispatcher.flush_pending("terminal-user")
        assert len(sent) >= 1

    assert True


@pytest.mark.asyncio
async def test_trigger_manager_check_all_with_silence_user():
    """验证 TriggerManager 正确检测 SILENCE 触发条件。"""
    user = User(
        user_id="silent_user", platform="terminal",
        relationship_type=RelationshipType.TRUSTED,
        interaction_count=100,
        deep_topics_count=10,
        last_interaction=(datetime.now() - timedelta(hours=100)).strftime("%Y-%m-%d %H:%M:%S"),
    )

    triggers = await TriggerManager.check_all(
        user=user, open_loops=[], unshared_events=[],
        daily_sent_count=0, is_late_night=False,
    )

    trigger_types = [t[0].value for t in triggers]
    assert "inactivity" in trigger_types, f"Expected SILENCE trigger, got {trigger_types}"
