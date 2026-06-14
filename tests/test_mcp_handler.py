"""tests/test_mcp_handler.py"""
import json
from wechat_mcp_server.mcp_handler import MCPHandler
from wechat_mcp_server.queue import MessageQueue


class TestMCPHandler:
    def setup_method(self):
        self.mq = MessageQueue()
        self.handler = MCPHandler(self.mq)

    def test_handle_initialize(self):
        result = self.handler.handle("initialize", {
            "protocolVersion": "2024-11-05",
            "clientInfo": {"name": "test"},
        })
        assert result["protocolVersion"] == "2024-11-05"
        assert result["serverInfo"]["name"] == "wechat-mcp-server"

    def test_handle_tools_list(self):
        result = self.handler.handle("tools/list", {})
        assert "tools" in result
        tool_names = [t["name"] for t in result["tools"]]
        assert "poll_messages" in tool_names
        assert "send_message" in tool_names
        assert "get_user_info" in tool_names
        assert "get_server_status" in tool_names

    def test_handle_tools_call_poll_messages(self):
        self.mq.push("openid_test", "text", "hello", "1")
        result = self.handler.handle("tools/call", {
            "name": "poll_messages",
            "arguments": {},
        })
        assert "content" in result
        text = result["content"][0]["text"]
        data = json.loads(text)
        # poll returns messages for all known users; cursor starts at 0
        # new user "openid_test" has cursor=0, so we scan from index 0
        assert len(data) >= 1
        assert data[0]["content"] == "hello"

    def test_handle_tools_call_unknown_tool(self):
        result = self.handler.handle("tools/call", {
            "name": "nonexistent",
            "arguments": {},
        })
        assert "error" in result

    def test_handle_unknown_method(self):
        result = self.handler.handle("unknown/method", {})
        assert "error" in result

    def test_handle_tools_call_send_message(self):
        """send_message should return success dict (actual API call will fail without real credentials)."""
        result = self.handler.handle("tools/call", {
            "name": "send_message",
            "arguments": {"user_openid": "test_user", "content": "hello"},
        })
        # Without real WeChat credentials, the API call will fail
        # but the handler should still return a valid result structure
        assert "content" in result
        text = result["content"][0]["text"]
        data = json.loads(text)
        assert "success" in data

    def test_handle_tools_call_get_server_status(self):
        result = self.handler.handle("tools/call", {
            "name": "get_server_status",
            "arguments": {},
        })
        assert "content" in result
        text = result["content"][0]["text"]
        data = json.loads(text)
        assert "uptime_seconds" in data
        assert "queue_size" in data
        assert data["status"] == "running"
