"""DB-backed life simulation scheduler."""

from datetime import datetime

import aiosqlite

from .catchup_planner import CatchupPlanner
from .life_generator import LifeGenerator
from .social_scheduler_adapter import SocialSchedulerAdapter
from ..storage import queries as q
from ..storage.models import LifeEvent


class LifeScheduler:
    """Advance Nan Gua's life when due.

    Being called does not mean an event is generated. The catchup planner is
    the gate.
    """

    def __init__(
        self,
        db: aiosqlite.Connection,
        llm=None,
        generator: LifeGenerator | None = None,
        social_adapter=None,
    ):
        self.db = db
        self.generator = generator or LifeGenerator()
        self.social_adapter = social_adapter or SocialSchedulerAdapter(db, llm)

    async def maybe_advance(
        self,
        user_message: str = "",
        now: datetime | None = None,
        diagnostics: dict | None = None,
    ) -> list[dict]:
        now = now or datetime.now()
        latest = await q.get_latest_life_event(self.db)
        last_at = self._parse_time(latest.get("created_at")) if latest else None
        decision = CatchupPlanner.plan(last_at, now)

        if diagnostics is not None:
            diagnostics["life_due"] = decision.due
            diagnostics["life_reason"] = decision.reason
            diagnostics["life_count"] = decision.count

        if not decision.due:
            return []

        generated: list[dict] = []
        for _ in range(decision.count):
            event = self.generator.generate(now=now, reason=decision.reason)
            saved = await q.insert_life_event(self.db, event)
            generated.append(self._life_event_to_dict(saved))

        try:
            if self._should_try_social(user_message, decision.reason):
                social_events = await self.social_adapter.maybe_advance(
                    user_message=user_message,
                    diagnostics=diagnostics,
                )
                generated.extend(social_events)
        except Exception:
            if diagnostics is not None:
                diagnostics["social_error"] = True

        return generated

    @staticmethod
    def _parse_time(value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _should_try_social(user_message: str, reason: str) -> bool:
        if reason not in {"regular", "catchup"}:
            return False
        known_names = [
            "wtt", "ccx", "mxt", "mcyy", "吴田田", "蔡楚娴", "毛雪婷", "颜姐",
        ]
        return any(name.lower() in user_message.lower() for name in known_names)

    @staticmethod
    def _life_event_to_dict(event: LifeEvent) -> dict:
        return {
            "event_id": event.event_id,
            "event_type": event.event_type,
            "category": event.category,
            "description": event.description,
            "characters_involved": event.characters_involved,
            "emotion": event.emotion,
            "causality_chain_id": event.causality_chain_id,
            "shared_with_users": event.shared_with_users,
            "created_at": event.created_at,
        }
