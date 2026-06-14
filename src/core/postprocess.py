"""Stage 4：短句拆分 + 异步 sidecar 任务编排。"""

import json
import re
import asyncio
import logging
from datetime import datetime

import aiosqlite

from .contracts import LLMResponse, OutgoingBurst, UserSession
from ..storage import queries as q
from ..storage.models import Message, Direction, RelationshipType, TriggerType
from ..memory.emotional_index import compute_weight, detect_emoji, extract_signals
from ..memory.summary_writer import SummaryWriter
from ..memory.loop_detector import LoopDetector
from ..relationship.branch_detector import (
    BranchDetector, detect_branch_signals, update_streak,
    should_activate_branch, should_retreat_branch,
)

logger = logging.getLogger(__name__)


class PostProcessor:
    """Stage 4：处理 LLM 回复，编排异步 sidecar 任务。"""

    def __init__(self, db: aiosqlite.Connection, llm=None,
                 summary_writer=None, loop_detector=None,
                 branch_detector=None,
                 self_memory=None,
                 persona_path: str = "",
                 self_md_path: str = "",
                 config: dict = None,
                 proactive_sender=None,
                 debug_logger=None):
        self.db = db
        self.llm = llm  # LLMEngine 实例（用于 open_loop 检测和摘要生成）
        self.summary_writer = summary_writer
        self.loop_detector = loop_detector
        self.branch_detector = branch_detector or BranchDetector(llm=llm)
        self._self_memory = self_memory
        self._persona_path = persona_path
        self._self_md_path = self_md_path
        self._config = config or {}
        self._proactive_sender = proactive_sender
        self._debug = debug_logger

    def set_proactive_sender(self, sender):
        """Set a runtime sender for proactive messages.

        sender signature: async (user_id: str, messages: list[str]) -> bool
        """
        self._proactive_sender = sender

    def process(self, response: LLMResponse) -> OutgoingBurst:
        """拆分短句。"""
        messages = self._split_bursts(response.reply_text)
        delay_ms = max(500, min(1500, sum(len(m) * 40 for m in messages) // len(messages)))
        return OutgoingBurst(messages=messages, delay_ms=delay_ms)

    async def run_sidecars(
        self,
        session: UserSession,
        incoming_text: str,
        response: LLMResponse,
        system_prompt: str,
    ):
        """fire-and-forget：记录消息 + 冷记忆 + 情感加权 + open_loop + 摘要检查 + 关系升级。"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        user_id = session.user.user_id
        hour = datetime.now().hour

        old_interaction = session.user.interaction_count
        old_deep = session.user.deep_topics_count
        old_late = session.user.late_night_count
        old_initiated = session.user.user_initiated_count
        old_relationship = session.user.relationship_type

        # 1. 记录消息（incoming + outgoing），捕获 message_id
        incoming_msg = await q.insert_message(self.db, Message(
            user_id=user_id,
            direction=Direction.INCOMING,
            content=incoming_text,
            deep_topic=response.deep_topic,
            created_at=now,
        ))
        outgoing_msg = await q.insert_message(self.db, Message(
            user_id=user_id,
            direction=Direction.OUTGOING,
            content=response.reply_text,
            persona_state=str(session.persona_state.__dict__),
            deep_topic=response.deep_topic,
            created_at=now,
        ))

        # 更新用户统计
        session.user.interaction_count += 1
        session.user.user_initiated_count += 1  # 用户主动发了一条消息
        if response.deep_topic:
            session.user.deep_topics_count += 1
        if hour >= 22 or hour <= 2:
            session.user.late_night_count += 1
        session.user.last_interaction = now
        await q.upsert_user(self.db, session.user)

        if self._debug:
            deep_mark = "deep_topic=True" if response.deep_topic else "deep_topic=False"
            late_mark = "late_night=True" if (hour >= 22 or hour <= 2) else "late_night=False"
            d_interaction = session.user.interaction_count - old_interaction
            d_deep = session.user.deep_topics_count - old_deep
            d_late = session.user.late_night_count - old_late
            d_initiated = session.user.user_initiated_count - old_initiated
            deltas = []
            if d_interaction: deltas.append(f"互动+{d_interaction}")
            if d_deep: deltas.append(f"深入+{d_deep}")
            if d_late: deltas.append(f"深夜+{d_late}")
            if d_initiated: deltas.append(f"主动+{d_initiated}")
            self._debug.sidecar(1, "✅", "保存对话",
                f"msg_{incoming_msg.message_id} → msg_{outgoing_msg.message_id}\n"
                f"标记: {deep_mark}, {late_mark}\n"
                f"本轮增量: {', '.join(deltas) if deltas else '无变化'}"
            )

        # 2. 冷记忆写入
        if response.worth_remembering:
            await q.append_user_note(self.db, user_id, response.worth_remembering)

        if self._debug:
            if response.worth_remembering:
                self._debug.sidecar(2, "✅", "记住新信息",
                    f'"{response.worth_remembering[:80]}"')
            else:
                self._debug.sidecar(2, "⏭️", "记住新信息", "无值得记录的内容")

        # 3. 情感加权
        has_emoji = detect_emoji(incoming_text)
        weight = compute_weight(
            deep_topic=response.deep_topic,
            hour=hour,
            msg_len=len(incoming_text),
            has_emoji=has_emoji,
        )
        signals = extract_signals(
            deep_topic=response.deep_topic,
            hour=hour,
            msg_len=len(incoming_text),
            has_emoji=has_emoji,
        )
        await q.insert_emotional_peak(
            self.db, user_id, message_id=incoming_msg.message_id, weight=weight,
            signals=signals,
        )

        if self._debug:
            signals_str = ", ".join(signals) if signals else "无"
            self._debug.sidecar(3, "✅", "情感峰值",
                f"权重 {weight}/3\n"
                f"触发信号: {signals_str}"
            )

        # 4. Open loop 检测（规则优先 + LLM 兜底）
        if self.loop_detector:
            try:
                loop_info = await self.loop_detector.detect(
                    incoming_text, system_prompt, message_id=incoming_msg.message_id,
                )
                if loop_info:
                    await q.insert_open_loop(
                        self.db, user_id,
                        description=loop_info["description"],
                        follow_up_window=loop_info.get("follow_up_window", ""),
                    )
            except Exception:
                pass

        if self._debug:
            has_loop = 'loop_info' in dir() and loop_info
            if self.loop_detector and has_loop:
                self._debug.sidecar(4, "✅", "待追问话题",
                    f'"{loop_info["description"]}"\n'
                    f'追问窗口: {loop_info.get("follow_up_window", "未指定")}'
                )
            elif self.loop_detector:
                self._debug.sidecar(4, "⏭️", "待追问话题", "未检测到")
            else:
                self._debug.sidecar(4, "⏭️", "待追问话题", "LoopDetector 未启用")

        # 5. 温记忆摘要检查
        count_since = 0
        if self.summary_writer:
            try:
                count_since = await q.get_message_count_since_last_summary(self.db, user_id)
                if count_since >= 50:
                    history = await q.get_recent_messages(self.db, user_id, limit=60)
                    time_span = SummaryWriter.compute_time_span(history)
                    summary = await self.summary_writer.generate(
                        system_prompt, history, session.user.display_name or "朋友",
                    )
                    # 写入摘要（含时间跨度）
                    full_summary = f"[{time_span}] {summary}"
                    await q.insert_summary(
                        self.db, user_id, full_summary,
                        range_start=0, range_end=outgoing_msg.message_id or 0,
                    )
                    # 提取话题关键词并写入 users.topics_discussed
                    topics = SummaryWriter.extract_topics(summary)
                    if topics:
                        existing = json.loads(session.user.topics_discussed or "[]")
                        for t in topics:
                            if t not in existing:
                                existing.append(t)
                        session.user.topics_discussed = json.dumps(existing, ensure_ascii=False)
                        await q.upsert_user(self.db, session.user)
            except Exception:
                pass

        if self._debug:
            cs = locals().get('count_since', 0)
            if cs >= 50:
                tops = locals().get('topics', [])
                self._debug.sidecar(5, "✅", "摘要生成",
                    f"{cs} 条达成\n"
                    f"新话题: {', '.join(tops) if tops else '无'}"
                )
            else:
                self._debug.sidecar(5, "⏭️", "摘要检查",
                    f"{cs}/50 条（还差 {50 - cs} 条）"
                )

        # 6. 关系升级检查
        await self._check_escalation(session.user)

        if self._debug:
            rel = session.user.relationship_type
            if rel != old_relationship:
                self._debug.sidecar(6, "✅", "关系升级",
                    f"{old_relationship.value} → {rel.value}"
                )
            else:
                ic = session.user.interaction_count
                dc = session.user.deep_topics_count
                uic = session.user.user_initiated_count
                if rel.value == "stranger":
                    gap = (f"深入话题还需 {max(0, 2 - dc)} 次 | "
                           f"互动还需 {max(0, 10 - ic)} 轮")
                elif rel.value == "acquaintance":
                    gap = (f"深入话题还需 {max(0, 5 - dc)} 次 | "
                           f"用户主动还需 {max(0, 5 - uic)} 次 | "
                           f"互动还需 {max(0, 50 - ic)} 轮")
                else:
                    gap = "已到自动升级上限，由分支检测接管"
                self._debug.sidecar(6, "⏭️", "关系升级",
                    f"{rel.value} → {rel.value}\n"
                    f"状态: 互动 {ic}, 深入 {dc}, 主动 {uic}\n"
                    f"升级检查: {gap}"
                )

        # 7. 分支检测 + 漂移（异步，下轮生效）
        await self._check_branch_drift(session, system_prompt)

        # 8. 主动消息触发检查（6 种触发器）
        await self._check_proactive_triggers(session, system_prompt)

        # 9. 社交模拟 tick（后台生成社交事件）
        await self._social_tick(session, incoming_text)

        # 10. 人格进化 tick（检查触发，执行反思+写回）
        await self._evolution_tick(session, incoming_text)

    async def _check_escalation(self, user):
        """检查关系升级逻辑。"""
        if user.relationship_type == RelationshipType.STRANGER:
            if user.interaction_count >= 10 and user.deep_topics_count >= 2:
                user.relationship_type = RelationshipType.ACQUAINTANCE
                await q.upsert_user(self.db, user)
                await q.log_relationship_event(
                    self.db, user.user_id, "escalation",
                    {"type": "stranger"}, {"type": "acquaintance"},
                )
        elif user.relationship_type == RelationshipType.ACQUAINTANCE:
            if (
                user.interaction_count >= 50
                and user.deep_topics_count >= 5
                and user.user_initiated_count >= 5
            ):
                user.relationship_type = RelationshipType.TRUSTED
                await q.upsert_user(self.db, user)
                await q.log_relationship_event(
                    self.db, user.user_id, "escalation",
                    {"type": "acquaintance"}, {"type": "trusted"},
                )

    async def _check_branch_drift(self, session: UserSession, system_prompt: str):
        """分支检测 + streak 漂移 + 切入/回退。

        只在 trusted 阶段触发。异步执行，结果影响下一轮。
        """
        user = session.user

        # 只在 trusted 阶段检测分支
        if user.relationship_type not in (
            RelationshipType.TRUSTED,
            RelationshipType.BROTHER,
            RelationshipType.RESPECTED,
            RelationshipType.CRUSH,
        ):
            if hasattr(self, '_debug') and self._debug:
                self._debug.sidecar(7, "⏭️", "分支信号",
                    f"无（关系阶段 {user.relationship_type.value}，不检测分支）"
                )
            return

        # 加载最近用户消息
        recent = await q.get_recent_messages(self.db, user.user_id, limit=30)
        if not recent:
            return

        # 检测分支方向（规则优先 + LLM 兜底）
        try:
            detected_branch = await self.branch_detector.detect_with_fallback(
                recent_messages=recent,
                interaction_count=user.interaction_count,
                late_night_count=user.late_night_count,
                user_initiated_count=user.user_initiated_count,
                current_relationship=user.relationship_type,
                system_prompt=system_prompt,
            )
        except Exception:
            return  # LLM 调用失败不阻塞 pipeline

        branch_relationships = {
            RelationshipType.BROTHER,
            RelationshipType.RESPECTED,
            RelationshipType.CRUSH,
        }

        def parse_branch(value: str | None) -> RelationshipType | None:
            if not value:
                return None
            try:
                branch = RelationshipType(value)
            except ValueError:
                return None
            return branch if branch in branch_relationships else None

        active_branch_type = (
            user.relationship_type
            if user.relationship_type in branch_relationships
            else None
        )
        current_branch_type = parse_branch(user.branch_type)

        # 分支关系本身是 active branch；branch_type 缺失时补齐，避免无法回退。
        if active_branch_type and current_branch_type != active_branch_type:
            current_branch_type = active_branch_type
            user.branch_type = active_branch_type.value

        if active_branch_type:
            signal_match = detected_branch == active_branch_type
            new_streak = update_streak(user.branch_signal_streak, signal_match)

            if should_retreat_branch(new_streak, active_branch_type):
                old_type = user.relationship_type.value
                old_branch = user.branch_type
                user.relationship_type = RelationshipType.TRUSTED
                user.branch_type = None
                user.branch_signal_streak = 0  # 回退后重置
                await q.upsert_user(self.db, user)
                await q.log_relationship_event(
                    self.db, user.user_id, "branch_retreat",
                    {"type": old_type, "branch": old_branch},
                    {"type": "trusted", "branch": None},
                )
                return

            if (
                new_streak != user.branch_signal_streak
                or user.branch_type != active_branch_type.value
            ):
                user.branch_signal_streak = new_streak
                user.branch_type = active_branch_type.value
                await q.upsert_user(self.db, user)
        else:
            if detected_branch:
                if current_branch_type == detected_branch:
                    new_streak = update_streak(user.branch_signal_streak, True)
                else:
                    current_branch_type = detected_branch
                    user.branch_type = detected_branch.value
                    new_streak = 1
            else:
                new_streak = update_streak(user.branch_signal_streak, False)
                if new_streak <= 0:
                    current_branch_type = None
                    user.branch_type = None

            if should_activate_branch(new_streak, None) and current_branch_type:
                old_type = user.relationship_type.value
                user.relationship_type = current_branch_type
                user.branch_type = current_branch_type.value
                user.branch_signal_streak = 0  # 切入后重置
                await q.upsert_user(self.db, user)
                await q.log_relationship_event(
                    self.db, user.user_id, "branch_activate",
                    {"type": old_type, "branch": None},
                    {
                        "type": current_branch_type.value,
                        "branch": current_branch_type.value,
                    },
                )
                return

            if (
                new_streak != user.branch_signal_streak
                or user.branch_type != (
                    current_branch_type.value if current_branch_type else None
                )
            ):
                user.branch_signal_streak = new_streak
                await q.upsert_user(self.db, user)

        if hasattr(self, '_debug') and self._debug:
            streak_info = ""
            if current_branch_type:
                if new_streak >= 0:
                    streak_info = (f"{current_branch_type.value} +{new_streak}"
                                   f"（连续 {new_streak}/5）")
                else:
                    streak_info = (f"{current_branch_type.value} {new_streak}"
                                   f"（回退信号 {abs(new_streak)}/10）")
            elif detected_branch:
                if new_streak > 0:
                    streak_info = (f"{detected_branch.value} +{new_streak}"
                                   f"（连续 {new_streak}/5）")
                else:
                    streak_info = f"无方向（streak={new_streak}）"
            else:
                streak_info = f"无方向（streak={new_streak}）"
            gap = ""
            if new_streak > 0 and not current_branch_type:
                gap = (f"，还差 {5 - new_streak} 轮触发切入"
                       if new_streak < 5 else "，已触发切入！")
            elif new_streak < 0 and current_branch_type:
                gap = (f"，还差 {abs(-10 - new_streak)} 轮回退"
                       if new_streak > -10 else "，已触发回退！")
            icon = "📈" if new_streak != 0 else "⏭️"
            self._debug.sidecar(7, icon, "分支信号", f"{streak_info}{gap}")

    async def _check_proactive_triggers(
        self, session: UserSession, system_prompt: str,
    ):
        """检查 6 种主动消息触发条件，生成消息并入队。"""
        if not self.llm:
            return

        user = session.user

        # 每日上限
        try:
            daily_count = await q.count_proactive_today(self.db, user.user_id)
        except Exception:
            daily_count = 0
        if daily_count >= 3:
            return

        # 深夜判断
        hour = datetime.now().hour
        is_late_night = hour >= 22 or hour <= 2

        # 加载 open_loops
        try:
            open_loops = await q.get_open_loops(self.db, user.user_id)
        except Exception:
            open_loops = []

        # 加载未分享的 life_events
        try:
            unshared = await q.get_unshared_life_events(self.db, user.user_id, limit=5)
        except Exception:
            unshared = []

        # 触发决策（纯逻辑，不调 LLM）
        from ..proactive.trigger_manager import TriggerManager
        triggers = await TriggerManager.check_all(
            user=user,
            open_loops=open_loops,
            unshared_events=unshared,
            daily_sent_count=daily_count,
            is_late_night=is_late_night,
        )

        if not triggers:
            return

        # 生成消息（调 LLM）
        for trigger_type, context in triggers:
            extra_context = context or ""
            try:
                msg = await self.llm.generate_proactive(
                    user_name=user.display_name or "朋友",
                    trigger_type=trigger_type.value,
                    context=extra_context,
                    system_prompt=system_prompt,
                    relationship_type=user.relationship_type.value,
                )
                if msg:
                    task_id = await q.enqueue_proactive(
                        self.db, user.user_id, trigger_type, msg,
                    )
                    if self._proactive_sender:
                        sent = await self._proactive_sender(user.user_id, [msg])
                        if sent and task_id:
                            await q.mark_proactive_sent(self.db, task_id)
                    # milestone 去重
                    if trigger_type == TriggerType.MILESTONE and context:
                        await q.log_relationship_event(
                            self.db, user.user_id,
                            f"milestone_{context}",
                            {}, {},
                        )
            except Exception:
                pass  # 单条失败不阻塞其他

        if hasattr(self, '_debug') and self._debug:
            from ..proactive.trigger_manager import TriggerManager
            diag = TriggerManager.diagnose_all(
                user=session.user,
                open_loops=open_loops,
                unshared_events=unshared,
                daily_sent_count=daily_count,
                is_late_night=is_late_night,
            )
            triggered = diag["triggered_types"]
            checks = []
            labels = {"inactivity": "沉默", "time_of_day": "深夜",
                      "milestone": "里程碑", "memory_trigger": "待追问",
                      "social_share": "分享", "life_story": "故事"}
            for key, res in diag["results"].items():
                if not res["allowed"]:
                    continue
                label = labels.get(key, key)
                icon = "✓" if res.get("triggered") else "✗"
                detail = ""
                if key == "inactivity":
                    detail = f"({res.get('last_interaction', '?')})"
                elif key == "milestone":
                    detail = (f"({res.get('interaction_count', 0)} 轮, "
                              f"最近 {res.get('value', '?')})")
                elif key == "memory_trigger":
                    detail = f"({'有' if res.get('has_open_loops') else '无'}待追问)"
                elif key in ("social_share", "life_story"):
                    detail = f"({'有' if res.get('has_unshared') else '无'}未分享)"
                checks.append(f"{label} {icon} {detail}".strip())
            self._debug.sidecar(8,
                "✅" if triggered else "⏭️", "主动消息",
                f"{'触发: ' + ', '.join(triggered) if triggered else '无触发'}（今日已发 {diag['daily_count']}/3）\n"
                f"逐一: {' | '.join(checks)}"
            )

    async def _social_tick(self, session: UserSession, user_message: str):
        """社交模拟：后台生成社交事件。失败不阻塞 pipeline。"""
        if not self.llm:
            return
        diag: dict = {}
        try:
            from ..social.scheduler import Scheduler
            if not hasattr(self, '_social_scheduler'):
                self._social_scheduler = Scheduler(
                    self.db, self.llm, system_prompt="",
                )
            events = await self._social_scheduler.tick(user_message, diagnostics=diag)
        except Exception:
            events = []
        if hasattr(self, '_debug') and self._debug:
            arc_count = diag.get("active_arcs_count", 0)
            arc_results = diag.get("arc_results", [])
            if arc_results:
                lines = [f"检查 {arc_count} 条活跃弧"]
                for a in arc_results:
                    trans = f"{a['old_state']}→{a['new_state']}"
                    evt = (f"\n     → \"{a['event_description']}\""
                           if a.get('event_description') else "（无事件）")
                    lines.append(
                        f"{a['character_name']}·{a['arc_type']} arc: "
                        f"{trans}, 事件 {a['event_count']}/{a['max_events']}{evt}"
                    )
                self._debug.sidecar(9, "🎭", "社交模拟", "\n".join(lines))
            elif arc_count > 0:
                self._debug.sidecar(9, "🎭", "社交模拟",
                    f"{arc_count} 条弧无新事件")
            else:
                self._debug.sidecar(9, "🎭", "社交模拟", "无活跃弧")

    async def _evolution_tick(self, session: UserSession, user_message: str):
        """人格进化：检查触发条件，执行反思+写回。失败不阻塞 pipeline。"""
        if not self.llm:
            return
        diag: dict = {}
        try:
            from ..evolution.engine import EvolutionEngine
            if not hasattr(self, '_evolution_engine'):
                self._evolution_engine = EvolutionEngine(
                    self.db, self.llm,
                    self_memory=getattr(self, '_self_memory', None),
                    persona_path=getattr(self, '_persona_path', ""),
                    self_md_path=getattr(self, '_self_md_path', ""),
                    config=getattr(self, '_config', {}),
                )
            executed = await self._evolution_engine.maybe_reflect(
                user_message, diagnostics=diag,
            )
        except Exception:
            executed = False
        if hasattr(self, '_debug') and self._debug:
            hours = diag.get("hours_since_last")
            reason = diag.get("trigger_reason")
            week = diag.get("week_count", 0)
            max_w = diag.get("max_per_week", 2)
            min_h = diag.get("min_interval_hours", 48)
            if executed or reason:
                self._debug.sidecar(10, "🌱", "人格进化",
                    f"触发！原因: {reason}\n"
                    f"本周 {week}/{max_w}，距上次 {hours}h"
                )
            else:
                parts = ["未触发"]
                if hours is not None:
                    parts.append(f"距上次 {hours}h（需 ≥{min_h}h）")
                else:
                    parts.append(f"距上次: 无记录（需 ≥{min_h}h）")
                parts.append(f"本周 {week}/{max_w}")
                events = []
                ev = diag
                if ev.get("event_aftermath_arcs", 0) > 0:
                    events.append(f"aftermath={ev['event_aftermath_arcs']}")
                if ev.get("event_corrections", 0) >= 3:
                    events.append(f"纠正={ev['event_corrections']}")
                if ev.get("event_branch_changes", 0) > 0:
                    events.append(f"分支={ev['event_branch_changes']}")
                if ev.get("event_consecutive_peaks", 0) >= 3:
                    events.append(f"峰值={ev['event_consecutive_peaks']}")
                parts.append(
                    f"事件: {', '.join(events) if events else '无触发事件'}"
                )
                self._debug.sidecar(10, "⏭️", "人格进化", "\n".join(parts))

    def _split_bursts(self, text: str) -> list[str]:
        """将 LLM 回复拆成短句连发。"""
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        if len(lines) >= 2:
            return [l for l in lines if l]
        bursts = re.split(r"(?<=[。！？!?])", text)
        bursts = [b.strip() for b in bursts if b.strip()]
        return bursts if bursts else [text]
