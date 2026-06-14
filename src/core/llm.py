"""LLM 引擎 — DeepSeek API + sidecar JSON 解析 + 重试 + 规则兜底。"""

import json
import os
import re
from typing import Optional

from openai import AsyncOpenAI
from openai import APIError, APIConnectionError, RateLimitError, APITimeoutError

from .contracts import PromptContext, LLMResponse

# 情感关键词（用于 JSON 解析失败时的 deep_topic 兜底检测）
EMOTION_KEYWORDS = [
    "感情", "分手", "难过", "焦虑", "喜欢", "爱", "家庭", "成长", "自己",
    "关系", "孤独", "害怕", "未来", "价值观", "emo", "崩溃", "哭",
]


class LLMEngine:
    """封装 DeepSeek API 调用（异步），含 sidecar JSON 解析。"""

    def __init__(
        self,
        model: str = "deepseek-chat",
        max_tokens: int = 1024,
        temperature: float = 0.8,
        api_key: Optional[str] = None,
        base_url: str = "https://api.deepseek.com",
    ):
        api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            raise ValueError("DEEPSEEK_API_KEY not set")
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self._retry_count = 2
        self._retry_delays = [1.0, 3.0]  # 秒

    async def chat(self, prompt_ctx: PromptContext) -> LLMResponse:
        """Stage 3 入口：发送消息 → 解析 sidecar JSON → 返回 LLMResponse。"""
        import asyncio

        # 把 sidecar instruction 追加到最后一条 user message
        messages = list(prompt_ctx.messages)
        last_msg = messages[-1]
        messages[-1] = {
            "role": last_msg["role"],
            "content": last_msg["content"] + "\n\n" + prompt_ctx.sidecar_instruction,
        }

        # 调 API（含重试）
        reply_text = None
        tokens = 0
        last_error = None

        for attempt in range(self._retry_count + 1):
            try:
                response = await self.client.chat.completions.create(
                    model=self.model,
                    max_tokens=self.max_tokens,
                    temperature=self.temperature,
                    messages=messages,
                )
                reply_text = response.choices[0].message.content
                tokens = response.usage.total_tokens if response.usage else 0
                break
            except (APIConnectionError, APITimeoutError, RateLimitError) as e:
                last_error = e
                if attempt < self._retry_count:
                    await asyncio.sleep(self._retry_delays[attempt])
                continue
            except APIError as e:
                last_error = e
                break

        # 全部重试失败 → 返回降级回复
        if reply_text is None:
            return LLMResponse(
                reply_text="hhhhh 刚刚卡了一下 你再说一遍",
                deep_topic=False,
                mood="neutral",
                sidecar_parse_ok=False,
            )

        # 解析 sidecar JSON
        sidecar = self._parse_sidecar(reply_text)
        clean_text = self._strip_json_block(reply_text)

        if sidecar:
            return LLMResponse(
                reply_text=clean_text,
                deep_topic=sidecar.get("deep_topic", False),
                mood=sidecar.get("mood", "neutral"),
                worth_remembering=sidecar.get("worth_remembering"),
                tokens=tokens,
                sidecar_parse_ok=True,
            )
        else:
            # JSON 解析失败 → 规则兜底
            return LLMResponse(
                reply_text=clean_text,
                deep_topic=self._fallback_deep_topic(prompt_ctx),
                mood=self._fallback_mood(prompt_ctx),
                worth_remembering=None,
                tokens=tokens,
                sidecar_parse_ok=False,
            )

    def _parse_sidecar(self, text: str) -> Optional[dict]:
        """从回复中提取 sidecar JSON 块。"""
        # 查找最后一个 JSON 对象
        json_match = re.findall(r'\{[^{}]*"deep_topic"[^{}]*\}', text)
        if not json_match:
            return None
        try:
            return json.loads(json_match[-1])
        except json.JSONDecodeError:
            return None

    def _strip_json_block(self, text: str) -> str:
        """移除回复中的 JSON 块和 sidecar instruction。"""
        # 移除 sidecar JSON
        text = re.sub(r'\{[^{}]*"deep_topic"[^{}]*\}', '', text)
        # 移除可能残留的 sidecar instruction 行
        text = re.sub(r'在你的回复末尾.*deep_topic.*', '', text)
        return text.strip()

    def _fallback_deep_topic(self, prompt_ctx: PromptContext) -> bool:
        """规则兜底：判断是否深度话题。"""
        fb = prompt_ctx.fallback_data
        if fb.get("is_late_night"):
            return True
        if fb.get("msg_len", 0) > 50 and fb.get("has_emotion_keywords", False):
            return True
        return False

    def _fallback_mood(self, prompt_ctx: PromptContext) -> str:
        """规则兜底：判断当前心情。"""
        if prompt_ctx.fallback_data.get("is_late_night"):
            return "reflective"
        return "neutral"

    async def detect_open_loop(self, user_message: str, system_prompt: str) -> Optional[dict]:
        """独立异步调用：检测用户消息中是否含未完待续的事件。

        Returns: {"description": "...", "follow_up_window": "..."} 或 None
        """
        prompt = (
            "分析下面这条消息，判断用户是否提到了一个未来会发生的事件"
            "（面试、考试、看病、旅行、deadline、见面等）。\n"
            "如果提到了，返回 JSON：\n"
            '{"has_loop": true, "description": "事件简述", "follow_up_window": "next_week/tomorrow/in_3_days"}\n'
            "如果没有提到未来事件，返回：\n"
            '{"has_loop": false}\n\n'
            f"消息：{user_message}"
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                max_tokens=128,
                temperature=0.3,  # 低温度——需要准确判断
                messages=messages,
            )
            raw = response.choices[0].message.content
            data = json.loads(raw)
            if data.get("has_loop"):
                return {"description": data["description"], "follow_up_window": data.get("follow_up_window", "")}
        except (json.JSONDecodeError, Exception):
            pass
        return None

    async def classify_branch(
        self, recent_user_messages: list[str], system_prompt: str,
    ) -> Optional[str]:
        """独立异步调用：判断用户最近消息属于哪种分支方向。

        Returns: "brother" / "respected" / "crush" / None（无法判断）

        仅在规则无法确定时调用——边界 case 兜底。
        """
        joined = "\n".join(f"- {m}" for m in recent_user_messages[-20:])
        prompt = (
            "分析下面用户最近的消息，判断他们和对话对象的关系属于哪种类型：\n\n"
            "1. **brother（兄弟/互损）** — 互怼、说脏话、互相吐槽，像哥们一样\n"
            "2. **respected（被尊重/被依赖）** — 用户频繁寻求建议、关心、倾诉\n"
            "3. **crush（暧昧/依赖）** — 用户表现出焦虑、想念、深夜情绪依赖\n\n"
            f"用户最近的消息：\n{joined}\n\n"
            "只返回一个单词：brother / respected / crush。如果无法判断，返回 none。"
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                max_tokens=16,
                temperature=0.3,
                messages=messages,
            )
            raw = response.choices[0].message.content.strip().lower()
            if raw in ("brother", "respected", "crush"):
                return raw
        except (json.JSONDecodeError, Exception):
            pass
        return None

    async def generate_summary(
        self, system_prompt: str, messages: list[dict], user_display_name: str
    ) -> str:
        """独立异步调用：生成温记忆摘要。"""
        prompt = (
            f"以下是南瓜和 {user_display_name} 近期的聊天记录。请用 3-5 句话总结这段时间你们聊了什么：\n"
            "涵盖：用户的情绪状态、他提到的生活变化、南瓜分享的事、反复出现的话题。\n"
            "用南瓜的说话风格写——口语化、模糊时间、不说精确日期。"
        )
        all_messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
            {"role": "user", "content": "\n---\n聊天记录：\n" + "\n".join(
                f"{'用户' if m['role'] == 'user' else '南瓜'}: {m['content'][:200]}"
                for m in messages[-50:]
            )},
        ]
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                max_tokens=256,
                temperature=0.7,
                messages=all_messages,
            )
            return response.choices[0].message.content
        except Exception:
            return "（摘要生成失败）"

    # ─── 保留旧 API（bot.py / proactive / social simulation 兼容）─────────────────

    async def chat_legacy(
        self,
        user_message: str,
        system_prompt: str,
        conversation_history: list[dict[str, str]],
        persona_state: Optional[dict] = None,
    ) -> tuple[str, dict]:
        """旧版 chat()——bot.py 兼容。返回 (reply_text, metadata)。"""
        messages = [{"role": "system", "content": system_prompt}]

        if persona_state:
            state_str = (
                f"当前状态：心情={persona_state.get('mood', 'neutral')}，"
                f"能量={persona_state.get('energy_level', 0.5)}，"
                f"深夜模式={'是' if persona_state.get('night_mode') else '否'}"
            )
            messages.append({"role": "system", "content": state_str})

        messages.extend(conversation_history)
        messages.append({"role": "user", "content": user_message})

        response = await self.client.chat.completions.create(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            messages=messages,
        )

        reply_text = response.choices[0].message.content

        metadata = {
            "deep_topic": False,
            "mood": "neutral",
            "usage": {
                "input_tokens": response.usage.prompt_tokens,
                "output_tokens": response.usage.completion_tokens,
            },
        }

        return reply_text, metadata

    async def generate_proactive(
        self,
        user_name: str,
        trigger_type: str,
        context: str,
        system_prompt: str,
        relationship_type: str,
    ) -> str:
        """生成主动发起的话题消息。"""
        trigger_prompt = (
            f"你在主动给你的朋友 {user_name} 发消息。触发类型：{trigger_type}。\n"
            f"背景：{context}\n"
            f"你们的关系：{relationship_type}\n\n"
            "你是在主动发起对话——不是回复。更像分享/关心/吐槽，不像是回答问题。"
            "自然一点，像朋友之间随手发的那种消息。短句。"
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": trigger_prompt},
        ]

        response = await self.client.chat.completions.create(
            model=self.model,
            max_tokens=256,
            temperature=0.9,
            messages=messages,
        )

        return response.choices[0].message.content

    async def generate_simulated_event(
        self,
        event_type: str,
        recent_events: list[str],
        system_prompt: str,
    ) -> dict:
        """生成社交模拟事件。"""
        recent = "\n".join(f"- {e}" for e in recent_events[-5:]) if recent_events else "（暂无近期事件）"
        event_prompt = (
            f"生成一个南瓜生活中发生的事件。\n"
            f"事件类型：{event_type}\n"
            f"最近发生的事：\n{recent}\n\n"
            '返回 JSON：{"description": "...", "emotion": "...", "characters": [...]}\n'
            "描述自然具体，符合南瓜的说话风格和行为模式。"
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": event_prompt},
        ]

        response = await self.client.chat.completions.create(
            model=self.model,
            max_tokens=256,
            temperature=0.9,
            messages=messages,
        )

        raw = response.choices[0].message.content
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"description": raw, "emotion": "neutral", "characters": []}
