"""输入组装 + LLM 反思调用 + 输出解析/校验。"""

import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class Reflector:
    """组装反思素材 -> 调 LLM -> 解析结构化 JSON 输出。"""

    _SYSTEM_PROMPT = (
        '你是“半个南瓜”的元认知层。你的任务是审视近期的对话和社交事件，'
        '产出三样东西：\n\n'
        '1. self_insights — 自我认知的更新\n'
        '2. persona_changes — 行为规则的调整\n'
        '3. growth_note — 本周一句话成长总结\n\n'
        '原则：\n'
        '- 不是所有信号都值得更新认知。只产出真正重要的洞察。\n'
        '- persona 改动要克制——改得太多反而失去人格稳定性。\n'
        '- 没有洞察就说空的。不要说“可能”、“也许”——不确定就跳过。\n'
        '- 不预设哪个关系更重要——自己判断本周哪个信号最强。\n\n'
        '返回 JSON（不要 markdown 包裹）：\n'
        '{"self_insights": [{"trigger": "...", "old_view": "...", '
        '"new_view": "...", "confidence": 0.7}], '
        '"persona_changes": [{"target_layer": "0|1|2", '
        '"rule_type": "add|modify|delete", '
        '"old_text": "原文（modify/delete必填）", '
        '"new_text": "新文本（add/modify必填）", '
        '"reason": "原因"}], '
        '"growth_note": "一句话总结"}'
    )

    @staticmethod
    def assemble_input(
        summaries: list[dict],
        recent_corrections: list[dict],
        recent_social_events: list[dict],
        emotional_peaks: list[dict],
        deep_ratio_change: float,
        late_night_ratio_change: float,
        self_md_sections: str,
        persona_baseline: str,
    ) -> str:
        """组装反思 prompt 的 user 部分。"""

        parts = []

        # Layer 1: 近期行为快照
        parts.append("## 近期行为快照\n")
        if summaries:
            for s in summaries[:3]:
                parts.append(f"- 对话摘要：{s.get('summary_text', '')}\n")
        if recent_corrections:
            parts.append(f"- 本周纠正次数：{len(recent_corrections)}\n")
            for c in recent_corrections:
                parts.append(f"  - {c.get('description', '')}\n")
        if recent_social_events:
            parts.append(f"- 本周社交事件数：{len(recent_social_events)}\n")
            for e in recent_social_events[:10]:
                parts.append(f"  - {e.get('description', '')}\n")
        if not (summaries or recent_corrections or recent_social_events):
            parts.append("（本周无显著行为快照）\n")

        # Layer 2: 情感信号
        parts.append("\n## 情感信号\n")
        if emotional_peaks:
            parts.append(f"- 情感峰值事件数：{len(emotional_peaks)}\n")
            for p in emotional_peaks[:10]:
                parts.append(f"  - weight={p.get('weight', 1)}: {p.get('signals', '')}\n")
        parts.append(f"- 深度话题占比变化：{deep_ratio_change:+.2f}\n")
        parts.append(f"- 深夜对话占比变化：{late_night_ratio_change:+.2f}\n")

        # Layer 3: 关联回顾
        parts.append("\n## 关联回顾\n")
        if self_md_sections:
            parts.append(self_md_sections)
        else:
            parts.append("（无关联历史章节）\n")

        # Layer 4: 当前人格基线
        parts.append("\n## 当前人格基线\n")
        parts.append(persona_baseline)

        return "".join(parts)

    @staticmethod
    def parse_response(raw: str) -> Optional[dict]:
        """解析 LLM 返回的 JSON，校验字段。返回 None 表示跳过写回。"""
        if not raw:
            return None

        # 提取 JSON（LLM 可能用 markdown 包裹）
        raw = raw.strip()
        if raw.startswith("```"):
            lines = raw.split("\n")
            lines = [l for l in lines if not l.startswith("```")]
            raw = "\n".join(lines)

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Reflector: JSON 解析失败")
            return None

        # 校验顶层字段
        insights = data.get("self_insights", [])
        changes = data.get("persona_changes", [])
        growth_note = data.get("growth_note", "")

        if not isinstance(insights, list) or not isinstance(changes, list):
            return None

        # 过滤无效 insight
        valid_insights = []
        for item in insights:
            if not isinstance(item, dict):
                continue
            if not item.get("trigger") or not item.get("new_view"):
                continue
            conf = item.get("confidence", 0.5)
            try:
                conf = float(conf)
            except (ValueError, TypeError):
                conf = 0.5
            if conf < 0.0 or conf > 1.0:
                continue
            valid_insights.append({
                "trigger": item["trigger"],
                "old_view": item.get("old_view", ""),
                "new_view": item["new_view"],
                "confidence": conf,
            })

        # 校验 persona_changes
        valid_changes = []
        for item in changes:
            if not isinstance(item, dict):
                continue
            rt = item.get("rule_type", "")
            if rt not in ("add", "modify", "delete"):
                continue
            tl = str(item.get("target_layer", ""))
            if tl not in ("0", "1", "2"):
                continue
            # modify/delete 必须有 old_text
            if rt in ("modify", "delete") and not item.get("old_text"):
                continue
            # add/modify 必须有 new_text
            if rt in ("add", "modify") and not item.get("new_text"):
                continue
            valid_changes.append({
                "target_layer": tl,
                "rule_type": rt,
                "old_text": item.get("old_text", ""),
                "new_text": item.get("new_text", ""),
                "reason": item.get("reason", ""),
            })

        # 如果原始 JSON 中有 persona_changes 但全部校验失败 -> 拒绝整个反思
        if changes and not valid_changes:
            return None

        # 原始 JSON 中两者都空 -> 跳过（LLM 明确表示无洞察）
        if not insights and not changes:
            return None

        return {
            "self_insights": valid_insights,
            "persona_changes": valid_changes,
            "growth_note": growth_note,
        }

    async def reflect(self, llm, input_text: str) -> Optional[dict]:
        """调用 LLM 执行反思，返回解析后的结构化结果。"""
        if not llm:
            return None
        try:
            response = await llm.client.chat.completions.create(
                model=llm.model,
                max_tokens=1024,
                temperature=0.6,
                messages=[
                    {"role": "system", "content": self._SYSTEM_PROMPT},
                    {"role": "user", "content": input_text},
                ],
            )
            raw = response.choices[0].message.content
            return self.parse_response(raw)
        except Exception:
            logger.exception("Reflector: LLM 调用失败")
            return None
