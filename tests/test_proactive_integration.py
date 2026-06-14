"""tests/test_proactive_integration.py — 主动消息集成测试。不需要 API key。"""
import pytest
from datetime import datetime, timedelta
from src.proactive.trigger_manager import TriggerManager
from src.storage.models import (
    RelationshipType, TriggerType, User,
)


def make_user(rel, interaction=50, last_interaction=None):
    return User(
        user_id="u1", platform="terminal",
        relationship_type=rel,
        interaction_count=interaction,
        last_interaction=last_interaction,
    )


@pytest.mark.asyncio
async def test_full_trigger_pipeline_no_triggers():
    """没有任何触发条件 → 返回空列表。"""
    user = make_user(RelationshipType.STRANGER,
                     interaction=5,  # 不在里程碑列表 {10,50,100,...}
                     last_interaction=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    triggers = await TriggerManager.check_all(
        user=user,
        open_loops=[],
        unshared_events=[],
        daily_sent_count=0,
        is_late_night=False,
    )
    # stranger 只有 milestone，但 5 不在关口列表
    assert len(triggers) == 0


@pytest.mark.asyncio
async def test_milestone_trigger_for_stranger():
    """stranger + 100 轮 → 触发 milestone。"""
    user = make_user(RelationshipType.STRANGER, interaction=100,
                     last_interaction=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    triggers = await TriggerManager.check_all(
        user=user,
        open_loops=[],
        unshared_events=[],
        daily_sent_count=0,
        is_late_night=False,
    )
    assert len(triggers) == 1
    assert triggers[0][0] == TriggerType.MILESTONE
    assert triggers[0][1] == "100"


@pytest.mark.asyncio
async def test_daily_limit_blocks_all():
    """今天已发 3 条 → 不再触发。"""
    user = make_user(RelationshipType.TRUSTED, interaction=100,
                     last_interaction=(datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d %H:%M:%S"))
    triggers = await TriggerManager.check_all(
        user=user,
        open_loops=[{"description": "test"}],
        unshared_events=[{"event_type": "social", "category": "daily", "description": "x"}],
        daily_sent_count=3,  # 已达上限
        is_late_night=True,
    )
    assert len(triggers) == 0


@pytest.mark.asyncio
async def test_inactivity_triggers_for_trusted():
    """trusted + 5天没来 → 触发 inactivity。"""
    user = make_user(RelationshipType.TRUSTED, interaction=100,
                     last_interaction=(datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d %H:%M:%S"))
    triggers = await TriggerManager.check_all(
        user=user,
        open_loops=[],
        unshared_events=[],
        daily_sent_count=0,
        is_late_night=False,
    )
    types = [t[0] for t in triggers]
    assert TriggerType.INACTIVITY in types


@pytest.mark.asyncio
async def test_stranger_only_milestone():
    """stranger 只有 milestone 能触发。"""
    user = make_user(RelationshipType.STRANGER, interaction=10,
                     last_interaction=(datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d %H:%M:%S"))
    triggers = await TriggerManager.check_all(
        user=user,
        open_loops=[{"description": "test"}],
        unshared_events=[{"event_type": "social", "category": "daily", "description": "x"}],
        daily_sent_count=0,
        is_late_night=True,
    )
    # 只有 milestone，其他全部被关系门槛挡住
    assert len(triggers) == 1
    assert triggers[0][0] == TriggerType.MILESTONE
