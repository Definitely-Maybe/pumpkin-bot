"""事件生成器——封装 LLM.generate_simulated_event()。"""

from typing import Optional


class EventGenerator:
    """调用 LLM 生成社交事件。"""

    def __init__(self, llm=None):
        self.llm = llm

    async def generate(
        self,
        character_name: str,
        character_traits: str,
        character_tension: str,
        arc_type: str,
        arc_phase: str,
        recent_events: list[str],
        system_prompt: str,
    ) -> Optional[dict]:
        """生成一个社交模拟事件。

        Returns: {"description": str, "emotion": str, "characters": list} | None
        """
        if not self.llm:
            return None

        prompt = (
            f"生成南瓜与 {character_name} 之间的一个事件。\n\n"
            f"{character_name} 的性格：{character_traits}\n"
            f"{character_name} 的核心矛盾：{character_tension}\n"
            f"当前故事弧类型：{arc_type}，阶段：{arc_phase}\n\n"
            "这是一个叙事弧的一部分——事件要在序列中有意义。不要孤立地生成。\n"
            "用南瓜的视角描述，口语化、有细节、有情绪。"
        )

        try:
            return await self.llm.generate_simulated_event(
                event_type="social",
                recent_events=recent_events[-5:],
                system_prompt=system_prompt + "\n" + prompt,
            )
        except Exception:
            return None
