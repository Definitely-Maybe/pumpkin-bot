"""Adapter that lets the life layer reuse the existing social scheduler."""

import aiosqlite


class SocialSchedulerAdapter:
    """Thin wrapper around src.social.scheduler.Scheduler."""

    def __init__(self, db: aiosqlite.Connection, llm=None, system_prompt: str = ""):
        from ..social.scheduler import Scheduler

        self.scheduler = Scheduler(db, llm, system_prompt=system_prompt)

    async def maybe_advance(
        self,
        user_message: str = "",
        diagnostics: dict | None = None,
    ) -> list[dict]:
        return await self.scheduler.tick(user_message=user_message, diagnostics=diagnostics)
