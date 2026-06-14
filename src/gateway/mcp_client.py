"""MCPHttpClient — 手写 JSON-RPC 2.0 客户端。"""

import json
import logging
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)


class MCPHttpClient:
    """通过 HTTP POST 调用 MCP server 的 tools。"""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self._id = 0
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None:
            self._session = aiohttp.ClientSession()
        return self._session

    def _build_request(self, method: str, params: dict) -> dict:
        self._id += 1
        return {
            "jsonrpc": "2.0",
            "id": self._id,
            "method": method,
            "params": params,
        }

    async def call(self, tool_name: str, arguments: dict = None) -> Optional[dict]:
        """调用 MCP tool，返回解析后的 result 或 None。"""
        if arguments is None:
            arguments = {}

        request = self._build_request("tools/call", {
            "name": tool_name,
            "arguments": arguments,
        })

        try:
            session = await self._get_session()
            async with session.post(
                f"{self.base_url}/mcp",
                json=request,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status != 200:
                    logger.warning(f"MCP call {tool_name}: HTTP {resp.status}")
                    return None
                data = await resp.json()
        except Exception:
            logger.exception(f"MCP call {tool_name}: network error")
            return None

        if "error" in data:
            logger.warning(f"MCP call {tool_name}: error {data['error']}")
            return None

        if "result" in data:
            return self._parse_result(data["result"])

        return None

    @staticmethod
    def _parse_result(result: dict):
        """从 MCP result 中提取内容。"""
        content = result.get("content", [])
        if not content:
            return None
        first = content[0]
        if first.get("type") == "text":
            text = first.get("text", "")
            try:
                return json.loads(text)
            except (json.JSONDecodeError, TypeError):
                return text
        return first

    async def initialize(self) -> bool:
        """MCP 握手。"""
        request = self._build_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "nan-gua-bot", "version": "1.0"},
        })
        try:
            session = await self._get_session()
            async with session.post(
                f"{self.base_url}/mcp",
                json=request,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                return resp.status == 200
        except Exception:
            return False

    async def close(self):
        if self._session:
            await self._session.close()
            self._session = None
