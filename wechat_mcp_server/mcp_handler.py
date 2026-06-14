"""MCP Handler — 手写 JSON-RPC 2.0 方法分发。"""

import json
import logging
import time
from typing import Optional

from .queue import MessageQueue
from .wechat import WeChatProtocol
from .config import WECHAT_APPID

logger = logging.getLogger(__name__)

TOOL_DEFINITIONS = [
    {
        "name": "poll_messages",
        "description": "获取自上次 poll 以来收到的新消息。返回所有有未读消息的用户的消息列表。",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "send_message",
        "description": "通过客服消息 API 向指定用户推送文本消息。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "user_openid": {"type": "string", "description": "用户 OpenID"},
                "content": {"type": "string", "description": "消息文本内容"},
            },
            "required": ["user_openid", "content"],
        },
    },
    {
        "name": "get_user_info",
        "description": "获取微信用户的基本信息（昵称、性别、城市等）。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "user_openid": {"type": "string", "description": "用户 OpenID"},
            },
            "required": ["user_openid"],
        },
    },
    {
        "name": "get_server_status",
        "description": "获取服务器运行状态。",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
]


class MCPHandler:
    """处理 MCP JSON-RPC 请求，分发到具体 tool。"""

    def __init__(self, queue: MessageQueue, start_time: Optional[float] = None):
        self.queue = queue
        self.start_time = start_time or time.time()

    def handle(self, method: str, params: dict) -> dict:
        """分发 JSON-RPC method。返回 result dict（不含 jsonrpc/id 外层）。"""
        if method == "initialize":
            return self._handle_initialize(params)
        elif method == "tools/list":
            return self._handle_tools_list()
        elif method == "tools/call":
            return self._handle_tools_call(params)
        else:
            return {"error": {"code": -32601, "message": f"Method not found: {method}"}}

    async def handle_async(self, method: str, params: dict) -> dict:
        """Async dispatcher for FastAPI request handlers."""
        if method == "initialize":
            return self._handle_initialize(params)
        elif method == "tools/list":
            return self._handle_tools_list()
        elif method == "tools/call":
            return await self._handle_tools_call_async(params)
        else:
            return {"error": {"code": -32601, "message": f"Method not found: {method}"}}

    def _handle_initialize(self, params: dict) -> dict:
        return {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "wechat-mcp-server", "version": "1.0"},
        }

    def _handle_tools_list(self) -> dict:
        return {"tools": TOOL_DEFINITIONS}

    def _handle_tools_call(self, params: dict) -> dict:
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})

        tool_funcs = {
            "poll_messages": self._tool_poll_messages,
            "send_message": self._tool_send_message,
            "get_user_info": self._tool_get_user_info,
            "get_server_status": self._tool_get_server_status,
        }

        func = tool_funcs.get(tool_name)
        if not func:
            return {"error": {"code": -32602, "message": f"Unknown tool: {tool_name}"}}

        try:
            result_text = func(arguments)
            return {
                "content": [{"type": "text", "text": json.dumps(result_text, ensure_ascii=False)}],
            }
        except Exception as e:
            return {"error": {"code": -32603, "message": str(e)}}

    async def _handle_tools_call_async(self, params: dict) -> dict:
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})

        if tool_name == "send_message":
            return {
                "content": [{"type": "text", "text": json.dumps({"success": False}, ensure_ascii=False)}],
            }

        return self._handle_tools_call(params)

    # ─── tool implementations ────────────────────────

    def _tool_poll_messages(self, args: dict) -> list:
        """返回所有已知用户的新消息。"""
        # 收集所有出现过的用户
        all_users = set(self.queue._cursors.keys())
        for item in self.queue._items:
            all_users.add(item["user_openid"])

        all_msgs = []
        for uid in all_users:
            msgs = self.queue.poll(uid)
            all_msgs.extend(msgs)
        return all_msgs

    def _tool_send_message(self, args: dict) -> dict:
        """同步包装异步 send_custom_message。"""
        import asyncio
        user_openid = args["user_openid"]
        content = args["content"]
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        success = loop.run_until_complete(
            WeChatProtocol.send_custom_message(user_openid, content)
        )
        return {"success": success}

    async def _tool_send_message_async(self, args: dict) -> dict:
        """Send a customer-service text message from an async request path."""
        user_openid = args["user_openid"]
        content = args["content"]
        success = await WeChatProtocol.send_custom_message(user_openid, content)
        return {
            "success": success,
            "appid": WECHAT_APPID,
            "error": WeChatProtocol._last_error,
        }

    def _tool_get_user_info(self, args: dict) -> dict:
        """获取用户信息（简化实现：返回 openid + 占位昵称）。"""
        return {
            "openid": args["user_openid"],
            "nickname": "微信用户",
            "note": "完整实现需要 access_token 调用 user/info API",
        }

    def _tool_get_server_status(self, args: dict) -> dict:
        uptime = int(time.time() - self.start_time)
        return {
            "uptime_seconds": uptime,
            "queue_size": self.queue.size,
            "status": "running",
        }
