"""WeChatAdapter — 通过 MCP client 与 WeChat MCP Server 通信。"""

import asyncio
import logging
from typing import Callable, Awaitable

from .adapter import Adapter
from .mcp_client import MCPHttpClient
from wechat_mcp_server.wechat import WeChatProtocol

logger = logging.getLogger(__name__)


class WeChatAdapter(Adapter):
    """微信公众号适配器。"""

    platform = "wechat"

    def __init__(self, mcp_client: MCPHttpClient, poll_interval: float = 2.0):
        self.mcp = mcp_client
        self.poll_interval = poll_interval
        self._running = False

    async def start(self, on_message: Callable[[str, str], Awaitable[None]]):
        """启动轮询循环，持续拉取微信消息。"""
        # MCP 握手
        ok = await self.mcp.initialize()
        if not ok:
            logger.error("WeChatAdapter: MCP 握手失败")
            return

        self._running = True
        logger.info("WeChatAdapter: 开始轮询")

        while self._running:
            try:
                msgs = await self.mcp.call("poll_messages")
                if msgs and isinstance(msgs, list):
                    for msg in msgs:
                        if not isinstance(msg, dict):
                            continue
                        user_id = msg.get("user_openid", "")
                        content = msg.get("content", "")
                        if user_id and content:
                            await on_message(user_id, content)
            except Exception:
                logger.exception("WeChatAdapter: poll 异常")

            await asyncio.sleep(self.poll_interval)

    async def send(self, user_id: str, messages: list[str]):
        """通过 MCP 推送回复。"""
        for text in messages:
            if not text.strip():
                continue
            try:
                result = await asyncio.wait_for(
                    self.mcp.call("send_message", {
                        "user_openid": user_id,
                        "content": text,
                    }),
                    timeout=5,
                )
                if isinstance(result, dict) and result.get("success"):
                    continue

                logger.warning("WeChatAdapter: MCP 发送失败，改用直接客服接口")
                success = await WeChatProtocol.send_custom_message(user_id, text)
                if not success:
                    logger.warning("WeChatAdapter: 直接客服消息发送失败")
                else:
                    logger.info("WeChatAdapter: 直接客服消息发送成功")
            except Exception:
                logger.exception("WeChatAdapter: MCP 发送异常，改用直接客服接口")
                try:
                    success = await WeChatProtocol.send_custom_message(user_id, text)
                    if not success:
                        logger.warning("WeChatAdapter: 直接客服消息发送失败")
                    else:
                        logger.info("WeChatAdapter: 直接客服消息发送成功")
                except Exception:
                    logger.exception("WeChatAdapter: 发送失败")

    async def stop(self):
        self._running = False
        await self.mcp.close()
