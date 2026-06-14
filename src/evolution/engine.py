"""EvolutionEngine — 触发检测 + 编排。"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
import aiosqlite

from .reflector import Reflector
from .writeback import WriteBack
from ..storage import queries as q
from ..persona.memory import SelfMemory

logger = logging.getLogger(__name__)


class EvolutionEngine:
    """人格进化引擎。"""

    _MIN_INTERVAL_HOURS = 48
    _MAX_PER_WEEK = 2

    def __init__(
        self,
        db: aiosqlite.Connection,
        llm=None,
        self_memory: Optional[SelfMemory] = None,
        persona_path: str = "",
        self_md_path: str = "",
        config: Optional[dict] = None,
    ):
        self.db = db
        self.llm = llm
        self.self_memory = self_memory
        self.persona_path = persona_path
        self.self_md_path = self_md_path
        self.config = config or {}
        self.reflector = Reflector()

    async def maybe_reflect(self, user_message: str = "",
                            diagnostics: dict = None) -> bool:
        """每轮对话后调用。满足触发条件时执行反思。返回是否执行了反思。"""
        if not self.llm:
            return False

        # 1. 检查触发条件
        trigger_reason = await self._should_reflect()

        if diagnostics is not None:
            # 距上次反射时间
            last = await q.get_last_evolution_entry(self.db)
            hours_since = None
            if last and last.get("created_at"):
                try:
                    from datetime import datetime
                    delta = datetime.now() - datetime.strptime(
                        last["created_at"], "%Y-%m-%d %H:%M:%S"
                    )
                    hours_since = delta.total_seconds() / 3600
                except (ValueError, TypeError):
                    pass
            diagnostics["hours_since_last"] = round(hours_since, 1) if hours_since else None
            diagnostics["min_interval_hours"] = self._MIN_INTERVAL_HOURS
            diagnostics["week_count"] = await self._count_reflections_this_week()
            diagnostics["max_per_week"] = self._MAX_PER_WEEK
            diagnostics["trigger_reason"] = trigger_reason
            diagnostics["has_activity"] = await self._has_weekly_activity()

            # 事件触发详情
            try:
                cursor = await self.db.execute(
                    "SELECT COUNT(*) as cnt FROM social_arcs WHERE status = 'aftermath'"
                )
                row = await cursor.fetchone()
                diagnostics["event_aftermath_arcs"] = row["cnt"] if row else 0
            except Exception:
                diagnostics["event_aftermath_arcs"] = 0

            try:
                cursor = await self.db.execute(
                    "SELECT COUNT(*) as cnt FROM corrections "
                    "WHERE created_at >= date('now', '-7 days', 'localtime')"
                )
                row = await cursor.fetchone()
                diagnostics["event_corrections"] = row["cnt"] if row else 0
            except Exception:
                diagnostics["event_corrections"] = 0

            try:
                cursor = await self.db.execute(
                    "SELECT COUNT(*) as cnt FROM relationship_events "
                    "WHERE event_type IN ('branch_activate','branch_retreat') "
                    "AND created_at >= date('now', '-7 days', 'localtime')"
                )
                row = await cursor.fetchone()
                diagnostics["event_branch_changes"] = row["cnt"] if row else 0
            except Exception:
                diagnostics["event_branch_changes"] = 0

            try:
                cursor = await self.db.execute(
                    "SELECT COUNT(*) as cnt FROM ("
                    "SELECT weight FROM emotional_peaks "
                    "WHERE weight = 3 "
                    "ORDER BY created_at DESC LIMIT 3"
                    ")"
                )
                row = await cursor.fetchone()
                diagnostics["event_consecutive_peaks"] = (
                    row["cnt"] if row and row["cnt"] >= 3 else 0
                )
            except Exception:
                diagnostics["event_consecutive_peaks"] = 0

        if not trigger_reason:
            return False

        # 2. 组装输入
        try:
            input_text = await self._assemble_input()
        except Exception:
            logger.exception("EvolutionEngine: 输入组装失败")
            return False

        # 3. LLM 反思
        try:
            result = await self.reflector.reflect(self.llm, input_text)
        except Exception:
            logger.exception("EvolutionEngine: LLM 反思失败")
            result = None

        # 4. 写回
        if result:
            try:
                versions_dir = str(
                    Path(self.self_md_path).parent / "versions"
                    if self.self_md_path
                    else Path(self.persona_path).parent / "versions"
                )
                # Snapshot
                if self.self_md_path:
                    WriteBack.snapshot(self.self_md_path, versions_dir, datetime.now().strftime("%Y-%m-%d"))
                if self.persona_path:
                    pers_content = Path(self.persona_path).read_text(encoding="utf-8")
                    ver = WriteBack._extract_version(pers_content) or "unknown"
                    WriteBack.snapshot(self.persona_path, versions_dir, f"v{ver}")

                # Changelog
                WriteBack.append_changelog(versions_dir, result, trigger_reason)

                # self.md 追加
                if self.self_md_path:
                    WriteBack.append_self_md(self.self_md_path, result, versions_dir)

                # persona.md 原位更新
                if self.persona_path and result.get("persona_changes"):
                    WriteBack.apply_persona_delta(
                        self.persona_path, result["persona_changes"], versions_dir,
                    )
            except Exception:
                logger.exception("EvolutionEngine: 写回失败")

        # 5. 写 evolution_log
        await self._log_reflection(result, trigger_reason)
        return True

    # ─── trigger logic ────────────────────────────────────────

    async def _should_reflect(self) -> Optional[str]:
        """检查是否应该触发反思。返回触发原因或 None。"""
        now = datetime.now()

        # 防刷：检查上次反射
        last = await q.get_last_evolution_entry(self.db)
        if last and self._within_min_interval(last.get("created_at"), self._MIN_INTERVAL_HOURS):
            return None

        # 每周上限
        week_count = await self._count_reflections_this_week()
        if self._weekly_cap_reached(week_count, self._MAX_PER_WEEK):
            return None

        evo_cfg = self.config.get("evolution", {})
        ref_cfg = evo_cfg.get("reflection", {})
        cfg_day = ref_cfg.get("day_of_week", 6)
        cfg_hour = ref_cfg.get("hour", 23)

        # 定时触发
        if self._check_scheduled(now.weekday(), now.hour, cfg_day, cfg_hour):
            has_activity = await self._has_weekly_activity()
            if has_activity:
                return "定时反思"

        # 事件驱动触发（加急）
        event_reason = await self._check_event_triggers()
        if event_reason:
            return event_reason

        return None

    async def _check_event_triggers(self) -> Optional[str]:
        """检查事件驱动触发。"""
        # 社交弧高潮结束
        try:
            arcs = await q.get_active_arcs(self.db)
            for arc_data in arcs:
                if arc_data.get("status") == "aftermath":
                    return "社交弧高潮结束"
        except Exception:
            pass

        # 用户纠正 ≥ 3 次本周
        try:
            cursor = await self.db.execute(
                """SELECT COUNT(*) as cnt FROM corrections
                   WHERE created_at >= date('now', '-7 days', 'localtime')"""
            )
            row = await cursor.fetchone()
            if row and row["cnt"] >= 3:
                return "本周用户纠正≥3次"
        except Exception:
            pass

        # 关系分支变化
        try:
            cursor = await self.db.execute(
                """SELECT COUNT(*) as cnt FROM relationship_events
                   WHERE event_type IN ('branch_activate', 'branch_retreat')
                   AND created_at >= date('now', '-7 days', 'localtime')"""
            )
            row = await cursor.fetchone()
            if row and row["cnt"] > 0:
                return "关系分支变化"
        except Exception:
            pass

        # 情感峰值连续 3 条 weight=3
        try:
            cursor = await self.db.execute(
                """SELECT signals FROM emotional_peaks
                   WHERE weight = 3
                   ORDER BY created_at DESC LIMIT 3"""
            )
            rows = await cursor.fetchall()
            if len(rows) >= 3:
                return "连续情感峰值"
        except Exception:
            pass

        return None

    async def _has_weekly_activity(self) -> bool:
        """检查本周是否有足够活动（≥10 轮对话或有社交事件）。"""
        try:
            cursor = await self.db.execute(
                """SELECT COUNT(*) as cnt FROM messages
                   WHERE created_at >= date('now', '-7 days', 'localtime')"""
            )
            row = await cursor.fetchone()
            msg_count = row["cnt"] if row else 0
            if msg_count >= 20:  # incoming + outgoing = 10 轮对话 ≈ 20 条消息
                return True
        except Exception:
            pass

        try:
            cursor = await self.db.execute(
                """SELECT COUNT(*) as cnt FROM life_events
                   WHERE event_type = 'social'
                   AND created_at >= date('now', '-7 days', 'localtime')"""
            )
            row = await cursor.fetchone()
            if row and row["cnt"] > 0:
                return True
        except Exception:
            pass

        return False

    # ─── input assembly ───────────────────────────────────────

    async def _assemble_input(self) -> str:
        """组装反思 prompt。"""
        # Layer 1
        summaries = await self._get_recent_summaries()
        corrections = await self._get_recent_corrections()
        social_events = await self._get_recent_social_events()

        # Layer 2
        peaks = await self._get_emotional_peaks()
        deep_change, late_change = await self._get_ratio_changes()

        # Layer 3: 关联回顾
        self_md_sections = ""
        if self.self_memory:
            keywords = self._extract_keywords(social_events, corrections)
            if keywords:
                self_md_sections = self.self_memory.search(" ".join(keywords))

        # Layer 4: 人格基线
        persona_baseline = self._read_persona_baseline()

        return Reflector.assemble_input(
            summaries=summaries,
            recent_corrections=corrections,
            recent_social_events=social_events,
            emotional_peaks=peaks,
            deep_ratio_change=deep_change,
            late_night_ratio_change=late_change,
            self_md_sections=self_md_sections,
            persona_baseline=persona_baseline,
        )

    async def _get_recent_summaries(self) -> list[dict]:
        try:
            cursor = await self.db.execute(
                "SELECT summary_text FROM summaries ORDER BY created_at DESC LIMIT 3"
            )
            return [dict(r) for r in await cursor.fetchall()]
        except Exception:
            return []

    async def _get_recent_corrections(self) -> list[dict]:
        try:
            cursor = await self.db.execute(
                "SELECT description FROM corrections WHERE created_at >= date('now', '-7 days', 'localtime')"
            )
            return [dict(r) for r in await cursor.fetchall()]
        except Exception:
            return []

    async def _get_recent_social_events(self) -> list[dict]:
        try:
            cursor = await self.db.execute(
                """SELECT description FROM life_events
                   WHERE event_type = 'social'
                   AND created_at >= date('now', '-7 days', 'localtime')
                   ORDER BY created_at DESC LIMIT 20"""
            )
            return [dict(r) for r in await cursor.fetchall()]
        except Exception:
            return []

    async def _get_emotional_peaks(self) -> list[dict]:
        try:
            cursor = await self.db.execute(
                """SELECT signals, weight FROM emotional_peaks
                   WHERE created_at >= date('now', '-7 days', 'localtime')
                   ORDER BY weight DESC LIMIT 10"""
            )
            return [dict(r) for r in await cursor.fetchall()]
        except Exception:
            return []

    async def _get_ratio_changes(self) -> tuple[float, float]:
        try:
            cursor = await self.db.execute(
                """SELECT COUNT(*) as cnt FROM messages
                   WHERE deep_topic = 1
                   AND created_at >= date('now', '-7 days', 'localtime')"""
            )
            row = await cursor.fetchone()
            recent_deep = row["cnt"] if row else 0

            cursor = await self.db.execute(
                """SELECT COUNT(*) as cnt FROM messages
                   WHERE created_at >= date('now', '-7 days', 'localtime')"""
            )
            row = await cursor.fetchone()
            total = row["cnt"] if row else 1

            deep_ratio = recent_deep / max(total, 1)
        except Exception:
            deep_ratio = 0.0

        try:
            cursor = await self.db.execute(
                """SELECT COUNT(*) as cnt FROM messages
                   WHERE created_at >= date('now', '-7 days', 'localtime')
                   AND CAST(strftime('%H', created_at) AS INTEGER) >= 22"""
            )
            row = await cursor.fetchone()
            recent_late = row["cnt"] if row else 0
            late_ratio = recent_late / max(total, 1)
        except Exception:
            late_ratio = 0.0

        return deep_ratio, late_ratio

    def _extract_keywords(self, social_events: list[dict], corrections: list[dict]) -> list[str]:
        """从社交事件和纠正中提取关键词用于 SelfMemory.search。"""
        known_names = ["wtt", "ccx", "mxt", "mcyy", "yanjielin", "taixiaodan",
                       "吴田田", "蔡楚娴", "毛雪婷", "颜佳琳", "台晓丹", "MCYY"]
        text = json.dumps(social_events + corrections, ensure_ascii=False)
        found = [n for n in known_names if n.lower() in text.lower()]
        return found[:5]

    def _read_persona_baseline(self) -> str:
        """读取 persona.md 的 Layer 0 + Layer 1。"""
        try:
            content = Path(self.persona_path).read_text(encoding="utf-8")
            l0 = content.find("## Layer 0")
            l2 = content.find("## Layer 2")
            if l0 == -1:
                return "（未找到 Layer 0）"
            end = l2 if l2 > l0 else len(content)
            return content[l0:end].strip()
        except Exception:
            return "（读取失败）"

    # ─── logging ──────────────────────────────────────────────

    async def _log_reflection(self, result: Optional[dict], trigger_reason: str):
        """写 evolution_log 记录。"""
        from ..storage.models import EvolutionEntry
        entry = EvolutionEntry(
            cycle_date=datetime.now().strftime("%Y-%m-%d"),
            behavior_patterns_checked=json.dumps(
                {
                    "trigger": trigger_reason,
                    "insights_count": len(result["self_insights"]) if result else 0,
                    "changes_count": len(result["persona_changes"]) if result else 0,
                },
                ensure_ascii=False,
            ),
            findings=json.dumps(
                result or {}, ensure_ascii=False,
            ),
            growth_notes=result.get("growth_note", "") if result else "",
            written_back=result is not None,
        )
        try:
            await q.insert_evolution_entry(self.db, entry)
        except Exception:
            logger.exception("EvolutionEngine: 日志写入失败")

    async def _count_reflections_this_week(self) -> int:
        try:
            cursor = await self.db.execute(
                """SELECT COUNT(*) as cnt FROM evolution_log
                   WHERE cycle_date >= date('now', 'weekday 0', '-7 days', 'localtime')"""
            )
            row = await cursor.fetchone()
            return row["cnt"] if row else 0
        except Exception:
            return 0

    # ─── classmethod helpers (testable) ───────────────────────

    @classmethod
    def _check_scheduled(cls, now_weekday: int, now_hour: int,
                         config_day: int, config_hour: int) -> bool:
        return now_weekday == config_day and now_hour == config_hour

    @classmethod
    def _within_min_interval(cls, last_reflection_str: Optional[str],
                             min_hours: int) -> bool:
        if not last_reflection_str:
            return False
        try:
            last = datetime.strptime(last_reflection_str, "%Y-%m-%d %H:%M:%S")
            return (datetime.now() - last).total_seconds() < min_hours * 3600
        except (ValueError, TypeError):
            return False

    @classmethod
    def _weekly_cap_reached(cls, count: int, max_per_week: int) -> bool:
        return count >= max_per_week
