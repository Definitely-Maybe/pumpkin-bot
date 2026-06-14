"""触发条件检查——6 种触发器，平台无关。"""

from datetime import datetime, timedelta
from typing import Optional

from ..storage.models import RelationshipType, TriggerType, User


class TriggerManager:
    """主动消息触发决策。所有 _check_* 方法都是纯逻辑（不调 LLM，不写 DB）。"""

    _MILESTONES = {10, 50, 100, 200, 365, 500, 1000}

    _RELATION_GATES: dict[TriggerType, set[RelationshipType]] = {
        TriggerType.INACTIVITY: {
            RelationshipType.ACQUAINTANCE,
            RelationshipType.TRUSTED,
            RelationshipType.BROTHER,
            RelationshipType.RESPECTED,
            RelationshipType.CRUSH,
        },
        TriggerType.MEMORY_TRIGGER: {
            RelationshipType.TRUSTED,
            RelationshipType.BROTHER,
            RelationshipType.RESPECTED,
            RelationshipType.CRUSH,
        },
        TriggerType.TIME_OF_DAY: {
            RelationshipType.TRUSTED,
            RelationshipType.BROTHER,
            RelationshipType.RESPECTED,
            RelationshipType.CRUSH,
        },
        TriggerType.MILESTONE: {
            RelationshipType.STRANGER,
            RelationshipType.ACQUAINTANCE,
            RelationshipType.TRUSTED,
            RelationshipType.BROTHER,
            RelationshipType.RESPECTED,
            RelationshipType.CRUSH,
        },
        TriggerType.SOCIAL_SHARE: {
            RelationshipType.TRUSTED,
            RelationshipType.BROTHER,
            RelationshipType.RESPECTED,
            RelationshipType.CRUSH,
        },
        TriggerType.LIFE_STORY: {
            RelationshipType.TRUSTED,
            RelationshipType.BROTHER,
            RelationshipType.RESPECTED,
            RelationshipType.CRUSH,
        },
    }

    _INACTIVITY_THRESHOLDS: dict[RelationshipType, int] = {
        RelationshipType.ACQUAINTANCE: 5,
        RelationshipType.TRUSTED: 3,
        RelationshipType.BROTHER: 2,
        RelationshipType.RESPECTED: 2,
        RelationshipType.CRUSH: 2,
    }

    # ─── public API ──────────────────────────────────────────

    @classmethod
    async def check_all(
        cls,
        user: User,
        open_loops: list[dict],
        unshared_events: list[dict],
        daily_sent_count: int,
        is_late_night: bool = False,
    ) -> list[tuple[TriggerType, Optional[str]]]:
        """检查所有触发条件，返回触发列表 [(type, context), ...]。

        context 是附加信息（如 milestone="100"），供 LLM generate_proactive 使用。
        每日上限 3 条在此处卡。
        """
        results: list[tuple[TriggerType, Optional[str]]] = []
        remaining = max(0, 3 - daily_sent_count)
        if remaining <= 0:
            return results

        rel = user.relationship_type

        # 1. inactivity（最高优先级）
        if cls._is_allowed(TriggerType.INACTIVITY, rel):
            if cls._check_inactivity(user):
                results.append((TriggerType.INACTIVITY, None))
                remaining -= 1
                if remaining <= 0:
                    return results

        # 2. memory_trigger
        if cls._is_allowed(TriggerType.MEMORY_TRIGGER, rel):
            if cls._check_memory_trigger(open_loops):
                results.append((TriggerType.MEMORY_TRIGGER, None))
                remaining -= 1
                if remaining <= 0:
                    return results

        # 3. time_of_day
        if cls._is_allowed(TriggerType.TIME_OF_DAY, rel):
            already_sent_tod = daily_sent_count > 0
            if cls._check_time_of_day(is_late_night, already_sent_tod):
                results.append((TriggerType.TIME_OF_DAY, None))
                remaining -= 1
                if remaining <= 0:
                    return results

        # 4. milestone
        if cls._is_allowed(TriggerType.MILESTONE, rel):
            milestone = cls._check_milestone(user)
            if milestone:
                results.append((TriggerType.MILESTONE, milestone))
                remaining -= 1
                if remaining <= 0:
                    return results

        # 5. social_share
        if cls._is_allowed(TriggerType.SOCIAL_SHARE, rel):
            if cls._check_social_share(unshared_events):
                results.append((TriggerType.SOCIAL_SHARE, None))
                remaining -= 1
                if remaining <= 0:
                    return results

        # 6. life_story
        if cls._is_allowed(TriggerType.LIFE_STORY, rel):
            if cls._check_life_story(unshared_events):
                results.append((TriggerType.LIFE_STORY, None))
                remaining -= 1

        return results

    @classmethod
    async def diagnose_all(
        cls,
        user: User,
        open_loops: list[dict],
        unshared_events: list[dict],
        daily_sent_count: int,
        is_late_night: bool = False,
    ) -> dict:
        """返回每条触发条件的检查结果，供 debug 使用。"""
        rel = user.relationship_type
        triggered = await cls.check_all(
            user, open_loops, unshared_events,
            daily_sent_count, is_late_night,
        )
        return {
            "daily_limit_reached": daily_sent_count >= 3,
            "daily_count": daily_sent_count,
            "results": {
                "inactivity": {
                    "allowed": cls._is_allowed(TriggerType.INACTIVITY, rel),
                    "triggered": (
                        cls._check_inactivity(user)
                        if cls._is_allowed(TriggerType.INACTIVITY, rel)
                        else False
                    ),
                    "last_interaction": user.last_interaction,
                },
                "time_of_day": {
                    "allowed": cls._is_allowed(TriggerType.TIME_OF_DAY, rel),
                    "is_late_night": is_late_night,
                    "triggered": (
                        cls._check_time_of_day(is_late_night, daily_sent_count > 0)
                        if cls._is_allowed(TriggerType.TIME_OF_DAY, rel)
                        else False
                    ),
                },
                "milestone": {
                    "allowed": cls._is_allowed(TriggerType.MILESTONE, rel),
                    "value": cls._check_milestone(user),
                    "interaction_count": user.interaction_count,
                },
                "memory_trigger": {
                    "allowed": cls._is_allowed(TriggerType.MEMORY_TRIGGER, rel),
                    "has_open_loops": len(open_loops) > 0,
                    "triggered": (
                        cls._check_memory_trigger(open_loops)
                        if cls._is_allowed(TriggerType.MEMORY_TRIGGER, rel)
                        else False
                    ),
                },
                "social_share": {
                    "allowed": cls._is_allowed(TriggerType.SOCIAL_SHARE, rel),
                    "has_unshared": len(unshared_events) > 0,
                    "triggered": (
                        cls._check_social_share(unshared_events)
                        if cls._is_allowed(TriggerType.SOCIAL_SHARE, rel)
                        else False
                    ),
                },
                "life_story": {
                    "allowed": cls._is_allowed(TriggerType.LIFE_STORY, rel),
                    "has_unshared": len(unshared_events) > 0,
                    "triggered": (
                        cls._check_life_story(unshared_events)
                        if cls._is_allowed(TriggerType.LIFE_STORY, rel)
                        else False
                    ),
                },
            },
            "triggered_types": [t[0].value for t in triggered],
        }

    # ─── relation gate ───────────────────────────────────────

    @classmethod
    def _is_allowed(cls, trigger: TriggerType, rel: RelationshipType) -> bool:
        gates = cls._RELATION_GATES.get(trigger, set())
        return rel in gates

    # ─── individual checks ───────────────────────────────────

    @classmethod
    def _check_inactivity(cls, user: User) -> bool:
        """用户多久没来了？"""
        threshold_days = cls._INACTIVITY_THRESHOLDS.get(user.relationship_type)
        if threshold_days is None:
            return False
        if not user.last_interaction:
            return False
        try:
            last = datetime.strptime(user.last_interaction, "%Y-%m-%d %H:%M:%S")
            elapsed = datetime.now() - last
            return elapsed >= timedelta(days=threshold_days)
        except (ValueError, TypeError):
            return False

    @classmethod
    def _check_memory_trigger(cls, open_loops: list[dict]) -> bool:
        """有没有可跟进的 open_loop？"""
        return len(open_loops) > 0

    @classmethod
    def _check_time_of_day(cls, is_late_night: bool, already_sent_today: bool) -> bool:
        """深夜时段触发？"""
        if already_sent_today:
            return False
        return is_late_night

    @classmethod
    def _check_milestone(cls, user: User) -> Optional[str]:
        """互动次数命中整数关口？"""
        if user.interaction_count in cls._MILESTONES:
            return str(user.interaction_count)
        return None

    @classmethod
    def _check_social_share(cls, unshared_events: list[dict]) -> bool:
        """有没有未分享的社交事件？"""
        for e in unshared_events:
            if e.get("event_type") == "social" and e.get("category") != "night_reflection":
                return True
        return False

    @classmethod
    def _check_life_story(cls, unshared_events: list[dict]) -> bool:
        """有没有未分享的生活趣事？"""
        for e in unshared_events:
            if e.get("category") == "daily":
                return True
            if e.get("event_type") == "life" and e.get("category") != "night_reflection":
                return True
        return False
