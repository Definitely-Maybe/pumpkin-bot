"""Decide whether Nan Gua's life should advance."""

from datetime import datetime, timedelta

from .types import CatchupDecision


class CatchupPlanner:
    """Pure due/catchup planner for life simulation."""

    REGULAR_INTERVAL = timedelta(hours=6)
    CATCHUP_THRESHOLD = timedelta(days=2)
    MAX_CATCHUP_EVENTS = 3

    @classmethod
    def plan(cls, last_event_at: datetime | None, now: datetime) -> CatchupDecision:
        if last_event_at is None:
            return CatchupDecision(due=True, count=1, reason="initial")

        elapsed = now - last_event_at
        if elapsed < cls.REGULAR_INTERVAL:
            return CatchupDecision(due=False, count=0, reason="cooldown")

        if elapsed >= cls.CATCHUP_THRESHOLD:
            days = max(1, elapsed.days)
            return CatchupDecision(
                due=True,
                count=min(cls.MAX_CATCHUP_EVENTS, days),
                reason="catchup",
            )

        return CatchupDecision(due=True, count=1, reason="regular")
