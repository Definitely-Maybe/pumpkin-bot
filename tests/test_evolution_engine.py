"""tests/test_evolution_engine.py"""
from datetime import datetime, timedelta
from src.evolution.engine import EvolutionEngine


class TestTriggerChecks:
    def test_scheduled_true_day_and_hour_match(self):
        """周日 23:00 匹配定时触发。"""
        assert EvolutionEngine._check_scheduled(
            now_weekday=6, now_hour=23,
            config_day=6, config_hour=23,
        ) is True

    def test_scheduled_false_wrong_day(self):
        assert EvolutionEngine._check_scheduled(
            now_weekday=0, now_hour=23,
            config_day=6, config_hour=23,
        ) is False

    def test_scheduled_false_wrong_hour(self):
        assert EvolutionEngine._check_scheduled(
            now_weekday=6, now_hour=10,
            config_day=6, config_hour=23,
        ) is False

    def test_min_interval_check(self):
        """48h 内刚反思过 → 不能再触发。"""
        recent = (datetime.now() - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
        assert EvolutionEngine._within_min_interval(recent, min_hours=48) is True

    def test_interval_expired(self):
        """超过 48h → 可以触发。"""
        old = (datetime.now() - timedelta(hours=50)).strftime("%Y-%m-%d %H:%M:%S")
        assert EvolutionEngine._within_min_interval(old, min_hours=48) is False

    def test_no_previous_reflection(self):
        """无历史记录 → 不卡间隔。"""
        assert EvolutionEngine._within_min_interval(None, min_hours=48) is False

    def test_weekly_cap_reached(self):
        """本周已 2 次 → 不再触发。"""
        assert EvolutionEngine._weekly_cap_reached(count=2, max_per_week=2) is True

    def test_weekly_cap_not_reached(self):
        assert EvolutionEngine._weekly_cap_reached(count=1, max_per_week=2) is False
