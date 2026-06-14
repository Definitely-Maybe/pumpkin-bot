"""Pipeline 编排器 — 串联 5 个阶段。替换 bot.py 的 _on_message。"""

import logging
import time
from typing import Optional

import aiosqlite

from .contracts import MessageContext, UserSession, PromptContext, LLMResponse, OutgoingBurst
from .session import SessionManager
from .context import ContextAssembler
from .llm import LLMEngine
from .postprocess import PostProcessor

logger = logging.getLogger(__name__)


class MessageBus:
    """Pipeline 编排器。每个 on_message 调用执行完整的 5 阶段流水线。"""

    def __init__(
        self,
        db: aiosqlite.Connection,
        session_mgr: SessionManager,
        context_asm: ContextAssembler,
        llm: LLMEngine,
        postprocessor: PostProcessor,
        adapters: list = None,  # list[Adapter]
        adapter = None,          # 单 adapter（向后兼容）
        debug_logger=None,       # 调试模式
    ):
        self.db = db
        self.session = session_mgr
        self.context = context_asm
        self.llm = llm
        self.postprocess = postprocessor
        self._debug = debug_logger
        # 支持 adapters 和 adapter 两种参数
        if adapters is not None:
            self.adapters = adapters
        elif adapter is not None:
            self.adapters = [adapter]
        else:
            self.adapters = []
        self.adapter = self.adapters[0] if self.adapters else None  # backward compat
        if hasattr(self.postprocess, "set_proactive_sender"):
            self.postprocess.set_proactive_sender(self.send_proactive)

    def _find_adapter(self, user_id: str):
        """根据 user_id 推断平台 adapter。"""
        for adapter in self.adapters:
            if adapter.platform == "terminal" and user_id == "terminal-user":
                return adapter
            if adapter.platform == "wechat" and not user_id.startswith("terminal"):
                return adapter
        # fallback: 第一个 adapter
        return self.adapters[0] if self.adapters else None

    async def send_proactive(self, user_id: str, messages: list[str]) -> bool:
        """发送主动消息到用户所属平台。"""
        adapter = self._find_adapter(user_id)
        if not adapter:
            return False
        await adapter.send(user_id, messages)
        return True

    async def on_message(self, user_id: str, text: str):
        """完整流水线：Adapter → Stage 1-4 → Adapter。"""
        adapter = self._find_adapter(user_id)
        if not adapter:
            return
        platform = adapter.platform

        t_start = time.time()

        try:
            # Stage 1: Session
            session = await self.session.resolve(user_id, platform)

            if self._debug:
                u = session.user
                self._debug.turn_start(user_id, platform, text)
                self._debug.session(
                    familiarity=u.familiarity_score,
                    rel_type=u.relationship_type.value,
                    interaction_count=u.interaction_count,
                    streak=u.branch_signal_streak,
                    branch_type=u.branch_type or "",
                )

            # Stage 2: Context
            prompt_ctx = await self.context.assemble(session, text)

            if self._debug:
                token_est = len(prompt_ctx.system_prompt) // 3
                # Count cold memory hits by searching for the cold-memory section
                cold_marker = "南瓜想起关于这个人的事"
                cold_idx = prompt_ctx.system_prompt.find(cold_marker)
                cold_hits = 0
                if cold_idx != -1:
                    section = prompt_ctx.system_prompt[cold_idx:]
                    cold_hits = section.count("\n- ")
                # Extract L4 section if present
                l4_start = prompt_ctx.system_prompt.find("## 当前关系行为规则")
                l4_str = ""
                if l4_start != -1:
                    l4_end = prompt_ctx.system_prompt.find("\n\n", l4_start + 10)
                    if l4_end == -1:
                        l4_end = min(l4_start + 300, len(prompt_ctx.system_prompt))
                    l4_str = prompt_ctx.system_prompt[l4_start:l4_end].replace("\n", " · ")
                self._debug.context(token_est, cold_hits, l4_str=l4_str)

            # Stage 3: LLM
            t_llm = time.time()
            response = await self.llm.chat(prompt_ctx)
            t_llm_elapsed = time.time() - t_llm

            if self._debug:
                in_est = len(prompt_ctx.system_prompt) // 3 + len(text) // 3
                out_est = len(response.reply_text) // 3
                self._debug.llm(
                    model=getattr(self.llm, 'model', 'deepseek-chat'),
                    elapsed=t_llm_elapsed,
                    in_tokens=in_est,
                    out_tokens=out_est,
                )
                self._debug.reply(response.reply_text)

            # Stage 4: PostProcess
            burst = self.postprocess.process(response)

            # Stage 5: Send
            await adapter.send(user_id, burst.messages)

            if self._debug:
                self._debug.sidecar_header()

            # Fire-and-forget sidecar tasks
            await self.postprocess.run_sidecars(
                session, text, response, prompt_ctx.system_prompt,
            )

            if self._debug:
                total = time.time() - t_start
                self._debug.turn_end(total)

        except Exception as e:
            logger.error(f"Pipeline error for user {user_id}: {e}")
            try:
                await adapter.send(user_id, ["hhhhh 刚刚卡了一下 你再说一遍"])
            except Exception:
                pass
