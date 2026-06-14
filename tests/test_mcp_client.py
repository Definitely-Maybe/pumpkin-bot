"""tests/test_mcp_client.py"""
import json
import pytest
from unittest.mock import AsyncMock, patch
from src.gateway.mcp_client import MCPHttpClient


class TestMCPHttpClient:
    def test_call_constructs_valid_jsonrpc_request(self):
        """验证 JSON-RPC 请求格式正确。"""
        client = MCPHttpClient("http://localhost:8090")
        request = client._build_request("tools/call", {
            "name": "poll_messages",
            "arguments": {},
        })
        assert request["jsonrpc"] == "2.0"
        assert request["method"] == "tools/call"
        assert request["params"]["name"] == "poll_messages"
        assert isinstance(request["id"], int)

    def test_call_increments_id(self):
        client = MCPHttpClient("http://localhost:8090")
        r1 = client._build_request("tools/list", {})
        r2 = client._build_request("tools/list", {})
        assert r2["id"] == r1["id"] + 1

    @staticmethod
    def _make_mock_response(status=200, json_data=None):
        """构建支持 async with 的 mock response。"""
        mock_resp = AsyncMock()
        mock_resp.status = status
        mock_resp.json = AsyncMock(return_value=json_data or {})
        mock_resp.__aenter__.return_value = mock_resp
        return mock_resp

    @pytest.mark.asyncio
    async def test_call_returns_result_on_success(self):
        client = MCPHttpClient("http://localhost:8090")
        mock_response = self._make_mock_response(json_data={
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"content": [{"type": "text", "text": '{"msgs": []}'}]},
        })
        with patch("aiohttp.ClientSession.post", return_value=mock_response):
            result = await client.call("poll_messages")
            assert result == {"msgs": []}

    @pytest.mark.asyncio
    async def test_call_returns_none_on_error(self):
        client = MCPHttpClient("http://localhost:8090")
        mock_response = self._make_mock_response(json_data={
            "jsonrpc": "2.0",
            "id": 1,
            "error": {"code": -32600, "message": "Invalid Request"},
        })
        with patch("aiohttp.ClientSession.post", return_value=mock_response):
            result = await client.call("poll_messages")
            assert result is None

    @pytest.mark.asyncio
    async def test_call_returns_none_on_network_error(self):
        client = MCPHttpClient("http://localhost:8090")
        with patch("aiohttp.ClientSession.post", side_effect=Exception("connection refused")):
            result = await client.call("poll_messages")
            assert result is None

    def test_text_result_parsed_correctly(self):
        """text content 是 JSON 字符串时自动解析。"""
        parsed = MCPHttpClient._parse_result({
            "content": [{"type": "text", "text": '{"key": "value"}'}],
        })
        assert parsed == {"key": "value"}

    def test_text_result_plain_text(self):
        """非 JSON 文本原样返回。"""
        parsed = MCPHttpClient._parse_result({
            "content": [{"type": "text", "text": "ok"}],
        })
        assert parsed == "ok"
