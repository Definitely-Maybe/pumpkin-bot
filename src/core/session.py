"""用户会话管理：查/建用户、对话历史、关系更新。"""

from datetime import datetime
from typing import Optional

import aiosqlite

from .contracts import UserSession
from ..storage import queries as q
from ..storage.models import (
    User, Message, RelationshipType, Direction, PersonaState,
)


class SessionManager:
    """管理每个用户的状态、历史和关系。"""

    def __init__(self, db_conn: aiosqlite.Connection):
        self.conn = db_conn

    async def get_or_create_user(
        self, user_id: str, platform: str = "terminal", display_name: Optional[str] = None
    ) -> User:
        """查找现有用户或创建新用户。"""
        user = await q.get_user(self.conn, user_id)
        if user is None:
            user = User(
                user_id=user_id,
                platform=platform,
                display_name=display_name or user_id,
                first_interaction=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            )
            await q.upsert_user(self.conn, user)
        elif display_name and user.display_name != display_name:
            user.display_name = display_name
        return user

    async def resolve(self, user_id: str, platform: str = "terminal") -> UserSession:
        """Stage 1 入口：查/建用户 → 加载历史 → 温记忆/冷记忆 → PersonaState。

        Returns: UserSession (dataclass)
        """
        # 查/建用户
        user = await self.get_or_create_user(user_id, platform)

        # 加载最近 30 条对话历史
        history = await self.get_history(user_id, limit=30)

        # 获取温记忆（最新摘要）
        warm_summary = await q.get_latest_summary(self.conn, user_id)

        # 获取冷记忆（users.notes）
        cold_notes = user.notes if user.notes else None

        # 实时计算熟悉度（同步，当前轮生效）
        from ..relationship.familiarity import compute_familiarity
        user.familiarity_score = compute_familiarity(
            interaction_count=user.interaction_count,
            deep_topics_count=user.deep_topics_count,
            late_night_count=user.late_night_count,
            user_initiated_count=user.user_initiated_count,
        )

        # 计算当前 PersonaState
        persona_state = await self.get_persona_state()

        return UserSession(
            user=user,
            relationship=user.relationship_type,
            persona_state=persona_state,
            history=history,
            warm_summary=warm_summary,
            cold_notes=cold_notes,
        )

    async def get_history(self, user_id: str, limit: int = 20) -> list[dict[str, str]]:
        return await q.get_recent_messages(self.conn, user_id, limit)

    async def record_exchange(
        self,
        user: User,
        incoming: str,
        outgoing: list[str],
        persona_state: dict,
        deep_topic: bool = False,
    ):
        """记录一轮完整的消息交换（用户来 + bot 回）。"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 记录用户消息
        await q.insert_message(self.conn, Message(
            user_id=user.user_id,
            direction=Direction.INCOMING,
            content=incoming,
            deep_topic=deep_topic,
            created_at=now,
        ))

        # 记录 bot 回复（多条短句合并为一条记录）
        combined = " | ".join(outgoing)
        await q.insert_message(self.conn, Message(
            user_id=user.user_id,
            direction=Direction.OUTGOING,
            content=combined,
            persona_state=str(persona_state),
            deep_topic=deep_topic,
            created_at=now,
        ))

        # 更新用户统计
        hour = datetime.now().hour
        is_late_night = hour >= 22 or hour <= 2
        user.interaction_count += 1
        if deep_topic:
            user.deep_topics_count += 1
        if is_late_night:
            user.late_night_count += 1
        user.last_interaction = now
        await q.upsert_user(self.conn, user)

    async def update_relationship(
        self,
        user: User,
        new_type: Optional[RelationshipType] = None,
        new_familiarity: Optional[float] = None,
        event_type: str = "update",
    ):
        """更新关系状态，并记录变更事件。"""
        old_state = {
            "type": user.relationship_type.value,
            "familiarity": user.familiarity_score,
        }
        if new_type:
            user.relationship_type = new_type
        if new_familiarity is not None:
            user.familiarity_score = new_familiarity
        new_state = {
            "type": user.relationship_type.value,
            "familiarity": user.familiarity_score,
        }
        await q.upsert_user(self.conn, user)
        await q.log_relationship_event(
            self.conn, user.user_id, event_type, old_state, new_state,
        )

    async def get_persona_state(self) -> PersonaState:
        """计算当前人格状态。"""
        now = datetime.now()
        hour = now.hour
        night_mode = hour >= 22 or hour <= 2
        return PersonaState(
            mood="reflective" if night_mode else "neutral",
            energy_level=0.3 if hour <= 2 else 0.7,
            night_mode=night_mode,
        )
