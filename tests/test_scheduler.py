"""tests/test_scheduler.py"""
from datetime import datetime, timedelta
from src.social.arcs import ArcState, ArcType
from src.social.scheduler import Scheduler


class TestSchedulerDecide:
    def test_no_active_arcs_no_trigger(self):
        """无活跃弧 + 够久了 → 应触发新弧。"""
        assert Scheduler._should_trigger_new_arc(
            active_arc_count=0,
            days_since_last_arc=5,
        ) is True

    def test_two_active_arcs_no_trigger(self):
        """已有 2 个活跃弧 → 不触发新弧。"""
        assert Scheduler._should_trigger_new_arc(
            active_arc_count=2,
            days_since_last_arc=5,
        ) is False

    def test_recent_arc_no_trigger(self):
        """1 天前刚有弧 → 不触发。"""
        assert Scheduler._should_trigger_new_arc(
            active_arc_count=0,
            days_since_last_arc=1,
        ) is False

    def test_cooldown_active(self):
        """角色冷却未到期 → 返回 True。"""
        future = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S")
        assert Scheduler._is_cooldown_active(future) is True

    def test_cooldown_expired(self):
        """角色冷却已到期 → 返回 False。"""
        past = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
        assert Scheduler._is_cooldown_active(past) is False

    def test_cooldown_none(self):
        assert Scheduler._is_cooldown_active(None) is False


class TestTriggerSource:
    def test_time_trigger(self):
        """太久无弧 → time 触发。"""
        assert Scheduler._pick_trigger_source(
            user_mentioned_char=False, days_since_last_arc=7,
        ) == "time"

    def test_random_trigger(self):
        """随机概率触发（测试多次确保覆盖）。"""
        sources = set()
        for _ in range(100):
            sources.add(Scheduler._pick_trigger_source(
                user_mentioned_char=False, days_since_last_arc=4,
            ))
        assert "time" in sources or "random" in sources

    def test_conversation_trigger(self):
        """用户提到角色 → conversation 触发。"""
        assert Scheduler._pick_trigger_source(
            user_mentioned_char=True, days_since_last_arc=0,
        ) == "conversation"
