"""温记忆摘要生成器 — 每 ~50 条消息触发 LLM 摘要 + 话题提取。"""


class SummaryWriter:
    """温记忆摘要生成。依赖 LLMEngine 实例。"""

    def __init__(self, llm):
        self.llm = llm

    async def generate(
        self,
        system_prompt: str,
        messages: list[dict],
        user_display_name: str,
    ) -> str:
        """生成摘要文本（委托给 LLMEngine）。"""
        return await self.llm.generate_summary(
            system_prompt, messages, user_display_name,
        )

    @staticmethod
    def extract_topics(summary_text: str) -> list[str]:
        """从摘要文本提取话题关键词（简单规则：匹配话题候选词）。"""
        topic_candidates = [
            "情绪", "焦虑", "工作", "家庭", "感情", "恋爱", "学业",
            "考试", "面试", "生活", "健康", "朋友", "父母", "金钱",
            "未来", "过去", "旅行", "游戏", "音乐", "电影", "书",
            "宠物", "猫", "狗", "食物", "运动", "社交", "孤独",
            "成长", "变化", "冲突", "和解", "梦想",
        ]
        found = []
        for topic in topic_candidates:
            if topic in summary_text:
                found.append(topic)
        return found

    @staticmethod
    def compute_time_span(messages: list[dict]) -> str:
        """估算消息覆盖的时间跨度。"""
        count = len(messages)
        if count <= 10:
            return "今天"
        elif count <= 30:
            return "最近一两天"
        elif count <= 60:
            return "最近几天"
        elif count <= 100:
            return "最近一两周"
        else:
            return "最近几周"
