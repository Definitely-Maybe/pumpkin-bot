"""CLI 终端适配器 — 用于本地测试。"""

import asyncio
import sys
from typing import Callable, Awaitable

from .adapter import Adapter


class TerminalAdapter(Adapter):
    """终端交互式聊天。"""

    platform = "terminal"

    def __init__(self, bot_name: str = "南瓜"):
        self.bot_name = bot_name
        self._running = False
        self._user_id = "terminal-user"

    async def start(self, on_message: Callable[[str, str], Awaitable[None]]):
        """启动终端聊天循环。"""
        self._running = True
        print(f"\n🎃 {self.bot_name} 已上线 (输入 /quit 退出)\n")

        while self._running:
            try:
                text = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: input("你: ")
                )
            except (EOFError, KeyboardInterrupt):
                break

            if text.strip().lower() in ("/quit", "/exit"):
                break

            if not text.strip():
                continue

            await on_message(self._user_id, text)

    async def send(self, user_id: str, messages: list[str]):
        """逐条打印 bot 回复。"""
        for msg in messages:
            # 模拟打字延迟
            delay = min(len(msg) * 0.05, 1.5)
            await asyncio.sleep(delay)
            print(f"{self.bot_name}: {msg}")
        print()  # 空行分隔

    async def stop(self):
        self._running = False
        print(f"\n{self.bot_name} 下线了~")
