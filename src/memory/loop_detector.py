"""情节记忆检测器 — 未完待续的事。"""

from typing import Optional
import aiosqlite


class LoopDetector:
    """Open loop 检测。依赖 LLMEngine 实例（可选）。"""

    # 规则兜底：关键词 → follow_up_window（不调 LLM，零成本）
    _TRIGGER_PATTERNS = [
        (["面试", "笔试", "面经"], "next_week"),
        (["考试", "期末", "期中", "复习"], "next_week"),
        (["医院", "体检", "看病", "手术"], "tomorrow"),
        (["旅行", "出去玩", "旅游", "出差"], "next_week"),
        (["deadline", "ddl", "截止", "汇报", "答辩"], "next_week"),
        (["见面", "约饭", "聚餐", "喝酒"], "in_3_days"),
        (["搬家", "换工作", "辞职", "入职"], "next_week"),
    ]

    def __init__(self, llm=None, db: Optional[aiosqlite.Connection] = None):
        self.llm = llm
        self.db = db

    def detect_by_rules(self, user_message: str) -> Optional[dict]:
        """规则检测未来事件（不调 LLM，零成本）。"""
        for patterns, window in self._TRIGGER_PATTERNS:
            for p in patterns:
                if p in user_message:
                    return {
                        "description": f"用户提到了：{p}",
                        "follow_up_window": window,
                        "method": "rules",
                    }
        return None

    async def detect(
        self,
        user_message: str,
        system_prompt: str,
        message_id: Optional[int] = None,
    ) -> Optional[dict]:
        """检测 open loop：先规则，规则没命中再调 LLM。

        Returns: {"description": str, "follow_up_window": str, "method": str} | None
        """
        # 1. 规则兜底（快、免费）
        rule_result = self.detect_by_rules(user_message)
        if rule_result:
            await self._mark_has_open_loop(message_id)
            return rule_result

        # 2. LLM 检测（慢、准确）
        if self.llm:
            result = await self.llm.detect_open_loop(user_message, system_prompt)
            if result:
                result["method"] = "llm"
                await self._mark_has_open_loop(message_id)
                return result

        return None

    async def _mark_has_open_loop(self, message_id: Optional[int]):
        """标记消息包含 open_loop。"""
        if self.db and message_id:
            try:
                await self.db.execute(
                    "UPDATE messages SET has_open_loop = 1 WHERE message_id = ?",
                    (message_id,),
                )
                await self.db.commit()
            except Exception:
                pass  # 列可能不存在（向后兼容）
