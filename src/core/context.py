"""Prompt 拼装器 — 分层组装：L0-3 常驻 + L4-5 按需 + self.md 检索 + 记忆层。"""

from datetime import datetime
from typing import Optional

import aiosqlite

from ..persona.rules import extract_layers, build_system_prompt
from ..persona.memory import SelfMemory
from ..persona.loader import load_persona_md
from ..storage.models import User
from .contracts import UserSession, PromptContext
from ..memory.cold_index import ColdIndex

class ContextAssembler:
    """Stage 2：构建每次 LLM 调用的完整 system prompt + messages。"""

    def __init__(self, persona_md_path: str, self_memory: SelfMemory, db: aiosqlite.Connection | None = None):
        persona_md = load_persona_md(persona_md_path)
        self.layers = extract_layers(persona_md)
        self.self_memory = self_memory
        self._persona_md_path = persona_md_path
        self.cold_index = ColdIndex()
        self.db = db

    def reload(self):
        """Hot-reload 时重新提取分层。"""
        persona_md = load_persona_md(self._persona_md_path)
        self.layers = extract_layers(persona_md)

    async def assemble(self, session: UserSession, user_message: str) -> PromptContext:
        """拼装完整 PromptContext。"""
        extra = []

        # 1. 时间上下文
        extra.append(self._build_time_context())

        # 2. 关系上下文
        extra.append(self._build_relationship_context(session.user))

        # 3. Layer 4 行为调整（按关系类型 + 熟悉度动态生成）
        from ..relationship.familiarity import build_layer4_context
        l4_context = build_layer4_context(session.relationship, session.user.familiarity_score)
        if l4_context:
            extra.append(l4_context)

        # 4. self.md 话题检索
        self_context = self.self_memory.search(user_message)
        if self_context:
            extra.append(self_context)

        # 5. 南瓜最近生活事件（可选素材，不强制分享）
        life_context = await self._build_life_context(session, user_message)
        if life_context:
            extra.append(life_context)

        # 6. 温记忆
        if session.warm_summary:
            extra.append(
                "## 你们之前的聊天（摘要）\n"
                f"南瓜记得这段时间和这个人聊了：{session.warm_summary}"
            )

        # 7. 冷记忆（关联触发：聊到猫 → 想起用户怕猫）
        if session.cold_notes:
            self.cold_index.build(session.cold_notes)
            triggered = self.cold_index.search(user_message, max_results=3)
            if triggered:
                extra.append(
                    "## 南瓜想起关于这个人的事\n"
                    "用模糊感觉而非精确数据——不要说日期、标签、原文：\n"
                    + "\n".join(f"- {t}" for t in triggered)
                )

        # 8. 重要记忆（情感加权召回）
        if self.db:
            from ..memory.recall_ranker import get_important_memories, format_important_memories
            important = await get_important_memories(self.db, session.user.user_id, limit=3)
            if important:
                extra.append(format_important_memories(important))

        # 拼 system prompt
        system_prompt = build_system_prompt(self.layers["L0_3"], extra)

        # 拼 messages（OpenAI 格式）
        messages = []
        messages.append({"role": "system", "content": system_prompt})
        messages.extend(session.history)
        messages.append({"role": "user", "content": user_message})

        # sidecar instruction
        sidecar_instruction = (
            "在你的回复末尾，附上一行 JSON（不要放在回复正文中，用户看不到）：\n"
            '{"deep_topic": true或false, "mood": "happy/neutral/sad/anxious/reflective",'
            ' "worth_remembering": "值得记住的事" 或 null}\n'
            "deep_topic=true 当本轮涉及情感/关系/家庭/价值观/自我认知等深度话题。\n"
            "worth_remembering 只写真正值得长期记住的事，日常闲聊填 null。"
        )

        # 兜底数据（JSON 解析失败时用）
        now = datetime.now()
        hour = now.hour
        fallback_data = {
            "is_late_night": hour >= 22 or hour <= 2,
            "msg_len": len(user_message),
            "has_emotion_keywords": any(
                kw in user_message
                for kw in ["感情", "分手", "难过", "焦虑", "喜欢", "爱", "家庭", "成长", "自己"]
            ),
        }

        return PromptContext(
            system_prompt=system_prompt,
            messages=messages,
            sidecar_instruction=sidecar_instruction,
            fallback_data=fallback_data,
        )

    def _build_time_context(self) -> str:
        now = datetime.now()
        hour = now.hour
        weekday = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][now.weekday()]
        night_mode = hour >= 22 or hour <= 2
        base = f"现在是 {weekday} {now.strftime('%H:%M')}。"
        if night_mode:
            base += " 深夜模式——反思深度增加，更脆弱、更口语化，可能带「妈的」「操」，暴露后接自嘲。"
        return base

    def _build_relationship_context(self, user: User) -> str:
        return (
            f"当前对话对象：{user.display_name or '朋友'}\n"
            f"你们的关系：{user.relationship_type.value}（熟悉度 {user.familiarity_score:.2f}）\n"
            f"互动次数：{user.interaction_count}，深度话题：{user.deep_topics_count}"
        )

    async def _build_life_context(self, session: UserSession, user_message: str) -> str:
        if not self.db:
            return ""
        try:
            from ..storage import queries as q
            from ..simulation.life_context_selector import LifeContextSelector
            from ..simulation.life_receptivity import LifeReceptivity

            events = await q.get_recent_life_events_for_user(
                self.db,
                session.user.user_id,
                limit=10,
                unshared_only=True,
            )
            messages = [*session.history, {"role": "user", "content": user_message}]
            receptivity = LifeReceptivity.estimate(messages)
            selector = LifeContextSelector()
            candidate = selector.select(session.user, user_message, events, receptivity)
            return selector.format_for_prompt(candidate)
        except Exception:
            return ""
