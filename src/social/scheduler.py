"""社交调度器——触发决策 + 事件生成编排。"""

import json
import random
import uuid
from datetime import datetime, timedelta
from typing import Optional
import aiosqlite

from .characters import CharacterManager
from .arcs import ArcStateMachine, ArcState, ArcType
from .event_generator import EventGenerator
from ..storage.models import SocialCharacter, SocialArc, LifeEvent
from ..storage import queries as q


class Scheduler:
    """社交调度：时间驱动 + 对话触发。"""

    _GLOBAL_COOLDOWN_MIN_DAYS = 3
    _GLOBAL_COOLDOWN_MAX_DAYS = 7
    _RANDOM_TRIGGER_CHANCE = 0.05
    _MAX_ACTIVE_ARCS = 2

    def __init__(self, db: aiosqlite.Connection, llm=None, system_prompt: str = ""):
        self.db = db
        self.llm = llm
        self.system_prompt = system_prompt
        self.char_manager = CharacterManager(db, llm)
        self.event_gen = EventGenerator(llm)

    # ─── public API ──────────────────────────────────────────

    async def tick(self, user_message: str = "",
                   diagnostics: dict = None) -> list[dict]:
        """每轮对话结束时调用。决定是否生成社交事件。

        Returns: 新生成的事件列表 [{"description": ..., ...}, ...]
        """
        if not self.llm:
            return []

        if diagnostics is not None:
            diagnostics["active_arcs_count"] = 0
            diagnostics["new_arc_started"] = False
            diagnostics["arc_results"] = []

        # 初始化角色（首次）
        await self.char_manager.get_or_init_characters()

        generated: list[dict] = []

        # 1. 检查现有活跃弧 —— 推进
        active_arcs = await q.get_active_arcs(self.db)
        if diagnostics is not None:
            diagnostics["active_arcs_count"] = len(active_arcs)
        for arc_data in active_arcs:
            arc = self._dict_to_arc(arc_data)
            old_state = arc.status
            event = await self._advance_arc(arc)
            if diagnostics is not None:
                char = await q.get_character(self.db, arc.character_id)
                diag = {
                    "character_name": char["name"] if char else "?",
                    "arc_type": arc.arc_type,
                    "old_state": old_state.value,
                    "new_state": arc.status.value,
                    "event_count": arc.event_count,
                    "max_events": arc.max_events,
                    "event_description": (
                        event.get("description", "")[:100] if event else None
                    ),
                }
                diagnostics["arc_results"].append(diag)
            if event:
                generated.append(event)

        # 2. 决定是否开始新弧
        if len(active_arcs) < self._MAX_ACTIVE_ARCS:
            user_mentioned = self._user_mentioned_character(user_message)
            chars = await self.char_manager.get_or_init_characters()
            fictional = [c for c in chars if c.source == "fictional"]

            trigger = self._pick_trigger_source(
                user_mentioned_char=user_mentioned,
                days_since_last_arc=self._days_since_last_arc(active_arcs),
            )

            if trigger:
                if diagnostics is not None:
                    diagnostics["new_arc_started"] = True
                new_arc = await self._start_new_arc(fictional, trigger)
                if new_arc:
                    event = await self._advance_arc(new_arc)
                    if event:
                        generated.append(event)

        return generated

    # ─── arc lifecycle ────────────────────────────────────────

    async def _advance_arc(self, arc: SocialArc) -> Optional[dict]:
        """推进弧：生成事件 + 状态转移。"""
        char = await q.get_character(self.db, arc.character_id)
        if not char:
            return None

        force_dormant = arc.event_count >= arc.max_events
        new_state, is_dormant = ArcStateMachine.advance(arc.status, force_dormant=force_dormant)

        if not force_dormant and new_state != ArcState.DORMANT:
            # 生成事件
            recent = await q.get_recent_life_events(self.db, limit=5)
            recent_descs = [e.get("description", "") for e in recent]

            event = await self.event_gen.generate(
                character_name=char["name"],
                character_traits=char["traits"],
                character_tension=char.get("core_tension", ""),
                arc_type=arc.arc_type,
                arc_phase=new_state.value,
                recent_events=recent_descs,
                system_prompt=self.system_prompt,
            )

            if event:
                await q.increment_arc_event_count(self.db, arc.arc_id)
                await self._save_event(char, arc, event, new_state)
                return event

        # 状态转移（无事件或强制休眠）
        await q.update_arc_status(self.db, arc.arc_id, new_state.value, ended=is_dormant)

        if is_dormant:
            # 设置冷却
            cool_days = random.randint(3, 7)
            cool_until = datetime.now() + timedelta(days=cool_days)
            await self._set_character_cooldown(arc.character_id, cool_until)

        return None

    async def _start_new_arc(self, fictional_chars: list[SocialCharacter], trigger: str) -> Optional[SocialArc]:
        """从虚构角色池中选择角色，开始新弧。"""
        eligible = [
            c for c in fictional_chars
            if not self._is_cooldown_active(c.arc_cooldown_until)
            and c.current_arc_id is None
        ]
        if not eligible:
            return None

        char = random.choice(eligible)
        arc_types = json.loads(char.allowed_arc_types or '["daily"]')
        arc_type = random.choice(arc_types)

        arc = SocialArc(
            arc_id=f"arc_{uuid.uuid4().hex[:12]}",
            character_id=char.character_id,
            arc_type=arc_type,
            status=ArcState.SETUP,
            trigger_source=trigger,
            max_events=ArcStateMachine.random_event_count(arc_type),
        )
        await q.insert_arc(self.db, arc)

        # 绑定到角色
        char.current_arc_id = arc.arc_id
        await q.upsert_character(self.db, char)

        return arc

    # ─── event persistence ────────────────────────────────────

    async def _save_event(self, char: dict, arc: SocialArc, event: dict, new_state: ArcState):
        """将生成的事件写入 life_events 表。"""
        life = LifeEvent(
            event_type="social",
            category="deep" if arc.arc_type in ("romance", "conflict") else "daily",
            description=event.get("description", ""),
            characters_involved=json.dumps([char["name"]], ensure_ascii=False),
            emotion=event.get("emotion", "neutral"),
            causality_chain_id=arc.arc_id,
        )
        await q.insert_life_event(self.db, life)

        # 转移弧状态
        await q.update_arc_status(self.db, arc.arc_id, new_state.value, ended=False)

    # ─── helpers ──────────────────────────────────────────────

    @classmethod
    def _should_trigger_new_arc(
        cls, active_arc_count: int, days_since_last_arc: int,
    ) -> bool:
        """检查是否应该触发新弧。"""
        if active_arc_count >= cls._MAX_ACTIVE_ARCS:
            return False
        if days_since_last_arc < cls._GLOBAL_COOLDOWN_MIN_DAYS:
            return False
        return True

    @classmethod
    def _is_cooldown_active(cls, cooldown_until: Optional[str]) -> bool:
        """检查角色冷却是否仍在生效。"""
        if not cooldown_until:
            return False
        try:
            until = datetime.strptime(cooldown_until, "%Y-%m-%d %H:%M:%S")
            return datetime.now() < until
        except (ValueError, TypeError):
            return False

    @classmethod
    def _pick_trigger_source(
        cls, user_mentioned_char: bool, days_since_last_arc: int,
    ) -> Optional[str]:
        """决定触发源。"""
        if user_mentioned_char:
            return "conversation"
        if days_since_last_arc >= cls._GLOBAL_COOLDOWN_MAX_DAYS:
            return "time"
        if random.random() < cls._RANDOM_TRIGGER_CHANCE:
            return "random"
        return None

    def _user_mentioned_character(self, message: str) -> bool:
        """检查用户消息是否提到了任何角色名。"""
        if not message:
            return False
        known_names = ["wtt", "ccx", "mxt", "mcyy", "吴田田", "蔡楚娴",
                       "豆豆", "毛雪婷", "马哥", "颜姐", "台老师",
                       "yanjielin", "taixiaodan"]
        for name in known_names:
            if name.lower() in message.lower():
                return True
        return False

    def _days_since_last_arc(self, active_arcs: list[dict]) -> int:
        """估算距离上一个弧过了多少天。"""
        if not active_arcs:
            return 999
        latest = max(
            (a.get("started_at", "") for a in active_arcs),
            default="",
        )
        if not latest:
            return 999
        try:
            started = datetime.strptime(latest, "%Y-%m-%d %H:%M:%S")
            return (datetime.now() - started).days
        except (ValueError, TypeError):
            return 999

    def _dict_to_arc(self, d: dict) -> SocialArc:
        """将 DB dict 转为 SocialArc 对象。"""
        return SocialArc(
            arc_id=d["arc_id"],
            character_id=d["character_id"],
            arc_type=d.get("arc_type", "daily"),
            status=ArcState(d.get("status", "setup")),
            trigger_source=d.get("trigger_source", ""),
            started_at=d.get("started_at"),
            ended_at=d.get("ended_at"),
            event_count=d.get("event_count", 0),
            max_events=d.get("max_events", 4),
        )

    async def _set_character_cooldown(self, character_id: str, cool_until: datetime):
        """设置角色冷却时间。"""
        await self.db.execute(
            "UPDATE social_characters SET arc_cooldown_until = ?, current_arc_id = NULL WHERE character_id = ?",
            (cool_until.strftime("%Y-%m-%d %H:%M:%S"), character_id),
        )
        await self.db.commit()
