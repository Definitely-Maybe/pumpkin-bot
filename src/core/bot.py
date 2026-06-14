"""南瓜 Bot 主循环 — 消息总线、组件组装。Phase 1：记忆 + 关系 + 纠正 + 热更新。"""

import asyncio
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

import aiosqlite

from ..gateway.terminal_adapter import TerminalAdapter
from ..persona.loader import load_persona_md
from ..persona.rules import parse_persona, PersonaRules
from ..persona.memory import SelfMemory
from ..persona.hot_reload import HotReload
from ..storage.db import init_db
from ..storage.models import User, RelationshipType
from ..utils.config import load_config
from .context import ContextAssembler
from .correction import CorrectionHandler
from .llm import LLMEngine
from .session import SessionManager
from .style_detector import StyleDetector


class NanGuaBot:
    """南瓜 Bot — 消息总线 + 所有组件的协调器。"""

    def __init__(self, config_path: str = "config.yaml"):
        self.config = load_config(config_path)
        self._running = False
        self._db: Optional[aiosqlite.Connection] = None
        self._adapter: Optional[TerminalAdapter] = None
        self._session: Optional[SessionManager] = None
        self._llm: Optional[LLMEngine] = None
        self._context: Optional[ContextAssembler] = None
        self._persona_rules: Optional[PersonaRules] = None
        self._self_memory: Optional[SelfMemory] = None
        self._correction: Optional[CorrectionHandler] = None
        self._style_detector: Optional[StyleDetector] = None
        self._hot_reload: Optional[HotReload] = None

    async def start(self):
        """启动 bot：初始化所有组件，开始消息循环。"""
        print("[bot] 正在启动南瓜 Bot...")

        # ---- 数据库 ----
        db_path = self.config["storage"]["db_path"]
        self._db = await init_db(db_path)
        print(f"[bot] 数据库已连接: {db_path}")

        # ---- 人格加载 ----
        persona_path = self.config["persona"]["persona_md_path"]
        self_md_path = self.config["persona"]["self_md_path"]
        skill_md_path = self.config["persona"]["skill_md_path"]
        persona_md = load_persona_md(persona_path)
        self._persona_rules = parse_persona(persona_md)
        print(f"[bot] 人格已加载: {persona_path}")

        # ---- self.md 检索器 ----
        self._self_memory = SelfMemory(self_md_path)
        print(f"[bot] self.md 检索器已就绪: {self_md_path}")

        # ---- LLM 引擎 ----
        llm_cfg = self.config["llm"]
        llm_kwargs = {
            "model": llm_cfg["model"],
            "max_tokens": llm_cfg["max_tokens"],
            "temperature": llm_cfg["temperature"],
        }
        if "base_url" in llm_cfg:
            llm_kwargs["base_url"] = llm_cfg["base_url"]
        self._llm = LLMEngine(**llm_kwargs)
        print(f"[bot] LLM 引擎已初始化: {llm_cfg['model']} ({llm_cfg['provider']})")

        # ---- 会话 + 上下文 + 风格检测 + 纠正 ----
        self._session = SessionManager(self._db)
        self._context = ContextAssembler(
            self._persona_rules, self._self_memory,
        )
        self._style_detector = StyleDetector()
        self._correction = CorrectionHandler(skill_md_path, self._db)
        print("[bot] 会话管理 / 风格检测 / 纠正机制已就绪")

        # ---- Hot-reload ----
        if self.config["persona"].get("hot_reload", True):
            self._hot_reload = HotReload()
            await self._hot_reload.watch(
                [persona_path, self_md_path, skill_md_path],
                self._on_files_changed,
            )
            print("[bot] hot-reload 已启动")

        # ---- 适配器 ----
        platform_cfg = self.config.get("platforms", {})
        if platform_cfg.get("terminal", {}).get("enabled", True):
            self._adapter = TerminalAdapter()
        else:
            raise RuntimeError("没有启用的平台适配器")

        # ---- 启动消息循环 ----
        self._running = True
        print("[bot] 启动完成！\n")
        await self._adapter.start(self._on_message)

    async def stop(self):
        """停止 bot。"""
        self._running = False
        if self._hot_reload:
            await self._hot_reload.stop()
        if self._adapter:
            await self._adapter.stop()
        if self._db:
            await self._db.close()
        print("[bot] 已停止")

    async def _on_files_changed(self, paths: set[str]):
        """hot-reload 触发：重载 persona.md / self.md。"""
        print(f"[bot] 🔄 检测到文件变化: {paths}")
        persona_path = self.config["persona"]["persona_md_path"]
        if any(str(Path(persona_path).resolve()) == p for p in paths):
            persona_md = load_persona_md(persona_path)
            self._persona_rules = parse_persona(persona_md)
            self._context.set_persona_rules(self._persona_rules)
            print("[bot] ✅ persona.md 已热更新")
        self_md_path = self.config["persona"]["self_md_path"]
        if any(str(Path(self_md_path).resolve()) == p for p in paths):
            self._self_memory.reload()
            print("[bot] ✅ self.md 已热更新")

    async def _on_message(self, user_id: str, text: str):
        """消息处理主流程 (Phase 1 完整版)。"""
        try:
            # 1. 查/建用户
            user = await self._session.get_or_create_user(
                user_id, self._adapter.platform,
            )
            # 统计用户主动发起
            history_count = len(await self._session.get_history(user_id, limit=1))
            if history_count > 0:
                user.user_initiated_count += 1

            # 2. 纠正检测
            correction_desc = self._correction.detect(text)
            if correction_desc:
                last_reply = await self._get_last_bot_reply(user_id)
                await self._correction.handle(user_id, text, last_reply)
                # 立即生效——追加到 system prompt
                print(f"[bot] 📝 检测到纠正: {correction_desc[:80]}...")

            # 3. 获取对话历史
            history = await self._session.get_history(user_id)

            # 4. 获取当前 persona 状态
            persona_state = await self._session.get_persona_state()

            # 5. 关系风格检测（acq+ → 分支）
            if user.relationship_type in (
                RelationshipType.TRUSTED, RelationshipType.ACQUAINTANCE,
            ):
                branch = self._style_detector.detect(user, history)
                if branch and branch != user.relationship_type:
                    old_type = user.relationship_type.value
                    await self._session.update_relationship(
                        user, new_type=branch,
                        event_type="escalation",
                    )
                    print(f"[bot] 🔀 关系分支: {old_type} → {branch.value}")

            # 6. 获取 Layer 4 行为规则（根据关系类型调整）
            layer4_rules = self._style_detector.get_layer4_rules(
                user.relationship_type,
            )

            # 7. 构建上下文 + system prompt
            system_prompt = self._context.build(
                text, user, history, persona_state.__dict__, layer4_rules,
            )

            # 8. LLM 推理
            reply_text, metadata = await self._llm.chat(
                text, system_prompt, history,
            )

            # 9. 后处理：拆短句
            messages = self._split_bursts(reply_text)

            # 10. 发送
            await self._adapter.send(user_id, messages)

            # 11. 记录 + 更新关系
            deep_topic = metadata.get("deep_topic", False)
            await self._session.record_exchange(
                user, text, messages, persona_state.__dict__, deep_topic,
            )

            # 12. 关系升级检查
            await self._check_relationship_escalation(user)

        except Exception as e:
            print(f"[bot] 处理消息时出错: {e}")
            try:
                await self._adapter.send(user_id, ["hhhhh 刚刚卡了一下", "你再说一遍"])
            except Exception:
                pass

    async def _get_last_bot_reply(self, user_id: str) -> Optional[str]:
        history = await self._session.get_history(user_id, limit=2)
        for msg in reversed(history):
            if msg.get("role") == "assistant":
                return msg["content"]
        return None

    async def _check_relationship_escalation(self, user: User):
        """检查是否满足关系升级条件。"""
        rel_cfg = self.config.get("relationship", {})

        if user.relationship_type == RelationshipType.STRANGER:
            threshold = rel_cfg.get("acquaintance_threshold", {})
            if (
                user.interaction_count >= threshold.get("min_interactions", 10)
                and user.deep_topics_count >= threshold.get("min_deep_topics", 2)
            ):
                await self._session.update_relationship(
                    user, new_type=RelationshipType.ACQUAINTANCE,
                    event_type="escalation",
                )

        elif user.relationship_type == RelationshipType.ACQUAINTANCE:
            threshold = rel_cfg.get("trusted_threshold", {})
            if (
                user.interaction_count >= threshold.get("min_interactions", 50)
                and user.deep_topics_count >= threshold.get("min_deep_topics", 5)
                and user.user_initiated_count >= threshold.get("min_user_initiated", 5)
            ):
                await self._session.update_relationship(
                    user, new_type=RelationshipType.TRUSTED,
                    event_type="escalation",
                )

    def _split_bursts(self, text: str) -> list[str]:
        """将 LLM 回复拆成短句连发（模拟南瓜的 7 字/条风格）。"""
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        if len(lines) >= 2:
            return lines
        bursts = re.split(r"(?<=[。！？!?])", text)
        bursts = [b.strip() for b in bursts if b.strip()]
        return bursts if bursts else [text]
