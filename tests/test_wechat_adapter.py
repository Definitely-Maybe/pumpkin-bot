"""tests/test_wechat_adapter.py"""
import pytest
from unittest.mock import AsyncMock, patch
from src.gateway.mcp_client import MCPHttpClient
from src.gateway.wechat_adapter import WeChatAdapter


class TestWeChatAdapter:
    def test_platform_is_wechat(self):
        client = MCPHttpClient("http://localhost:8090")
        adapter = WeChatAdapter(client)
        assert adapter.platform == "wechat"

    @pytest.mark.asyncio
    async def test_send_calls_mcp(self):
        client = MCPHttpClient("http://localhost:8090")
        client.call = AsyncMock(return_value={"success": True})
        adapter = WeChatAdapter(client)
        await adapter.send("openid_1", ["你好", "第二句"])
        assert client.call.call_count == 2
        # 第一句
        call_args = client.call.call_args_list[0]
        assert call_args[0][0] == "send_message"
        assert call_args[0][1]["user_openid"] == "openid_1"
        assert call_args[0][1]["content"] == "你好"

    @pytest.mark.asyncio
    async def test_send_empty_messages(self):
        client = MCPHttpClient("http://localhost:8090")
        client.call = AsyncMock()
        adapter = WeChatAdapter(client)
        await adapter.send("u", [])
        client.call.assert_not_called()
