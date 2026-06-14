"""tests/test_multi_platform_integration.py

集成测试：验证 MCP client ↔ handler 往返、Adapter ABC 合规性、XML 边界情况。
"""
import json
import pytest
from unittest.mock import AsyncMock, patch
from wechat_mcp_server.queue import MessageQueue
from wechat_mcp_server.mcp_handler import MCPHandler
from wechat_mcp_server.wechat import WeChatProtocol
from src.gateway.mcp_client import MCPHttpClient
from src.gateway.wechat_adapter import WeChatAdapter
from src.gateway.adapter import Adapter


class TestMCPRoundTrip:
    """MCP client ↔ handler 往返测试。"""

    def test_client_request_to_handler_tools_list(self):
        """模拟 client 构造 tools/list 请求 → handler 处理 → 验证返回。"""
        mq = MessageQueue()
        handler = MCPHandler(mq)

        # handler 处理 tools/list
        result = handler.handle("tools/list", {})
        assert "tools" in result

        # 验证 4 个 tool 都存在
        tool_names = [t["name"] for t in result["tools"]]
        assert "poll_messages" in tool_names
        assert "send_message" in tool_names
        assert "get_user_info" in tool_names
        assert "get_server_status" in tool_names

    def test_poll_messages_roundtrip(self):
        """推入消息 → handler poll → 返回 client 可解析的 JSON。"""
        mq = MessageQueue()
        handler = MCPHandler(mq)

        mq.push("openid_test", "text", "hello world", "1")

        result = handler.handle("tools/call", {
            "name": "poll_messages",
            "arguments": {},
        })
        text = result["content"][0]["text"]
        data = json.loads(text)
        assert isinstance(data, list)
        assert len(data) >= 1
        # 新用户首次 poll 应返回消息（cursor 初始为 0）
        contents = [m["content"] for m in data]
        assert "hello world" in contents

    def test_poll_messages_two_users_independent(self):
        """两个用户的消息互不干扰。"""
        mq = MessageQueue()
        handler = MCPHandler(mq)

        mq.push("user_a", "text", "msg from A", "1")
        mq.push("user_b", "text", "msg from B", "2")

        result = handler.handle("tools/call", {
            "name": "poll_messages",
            "arguments": {},
        })
        text = result["content"][0]["text"]
        data = json.loads(text)
        assert len(data) == 2
        users = {m["user_openid"] for m in data}
        assert users == {"user_a", "user_b"}

    def test_send_message_tool_returns_structure(self):
        """send_message 返回正确的结构（即使无真实微信凭证）。"""
        mq = MessageQueue()
        handler = MCPHandler(mq)

        result = handler.handle("tools/call", {
            "name": "send_message",
            "arguments": {"user_openid": "test_user", "content": "hello"},
        })
        assert "content" in result
        text = result["content"][0]["text"]
        data = json.loads(text)
        assert "success" in data

    def test_initialize_roundtrip(self):
        """MCP 握手返回正确的协议版本。"""
        mq = MessageQueue()
        handler = MCPHandler(mq)

        result = handler.handle("initialize", {
            "protocolVersion": "2024-11-05",
            "clientInfo": {"name": "nan-gua-bot", "version": "1.0"},
        })
        assert result["protocolVersion"] == "2024-11-05"
        assert result["serverInfo"]["name"] == "wechat-mcp-server"


class TestAdapterABCCompliance:
    """验证两个 Adapter 都遵循 ABC 接口。"""

    def test_terminal_adapter_is_adapter_instance(self):
        from src.gateway.terminal_adapter import TerminalAdapter
        ta = TerminalAdapter()
        assert isinstance(ta, Adapter)
        assert ta.platform == "terminal"

    def test_wechat_adapter_is_adapter_instance(self):
        client = MCPHttpClient("http://localhost:8090")
        wa = WeChatAdapter(client)
        assert isinstance(wa, Adapter)
        assert wa.platform == "wechat"

    def test_both_adapters_have_required_methods(self):
        """两个 Adapter 都实现了 start 和 send。"""
        from src.gateway.terminal_adapter import TerminalAdapter
        ta = TerminalAdapter()
        assert callable(ta.start)
        assert callable(ta.send)

        client = MCPHttpClient("http://localhost:8090")
        wa = WeChatAdapter(client)
        assert callable(wa.start)
        assert callable(wa.send)


class TestXMLParsingEdgeCases:
    """微信 XML 解析边界情况。"""

    def test_empty_xml_returns_none(self):
        assert WeChatProtocol.parse_message("") is None

    def test_malformed_xml_returns_none(self):
        assert WeChatProtocol.parse_message("<xml><ToUserName>gh") is None

    def test_not_xml_returns_none(self):
        assert WeChatProtocol.parse_message("not xml at all") is None

    def test_unknown_msg_type_returns_unsupported_hint(self):
        xml = """<xml>
            <ToUserName>gh_123</ToUserName>
            <FromUserName>openid_abc</FromUserName>
            <MsgType>video</MsgType>
            <MsgId>10003</MsgId>
        </xml>"""
        msg = WeChatProtocol.parse_message(xml)
        assert msg is not None
        assert "不支持" in msg["content"]
        assert msg["msg_type"] == "video"

    def test_voice_message_returns_unsupported_hint(self):
        xml = """<xml>
            <ToUserName>gh_123</ToUserName>
            <FromUserName>openid_abc</FromUserName>
            <CreateTime>1234567890</CreateTime>
            <MsgType>voice</MsgType>
            <MediaId>media_id_123</MediaId>
            <Format>amr</Format>
            <MsgId>10004</MsgId>
        </xml>"""
        msg = WeChatProtocol.parse_message(xml)
        assert msg is not None
        assert msg["content"] == "[语音消息——暂不支持]"

    def test_event_message_returns_event_hint(self):
        xml = """<xml>
            <ToUserName>gh_123</ToUserName>
            <FromUserName>openid_abc</FromUserName>
            <CreateTime>1234567890</CreateTime>
            <MsgType>event</MsgType>
            <Event>subscribe</Event>
            <MsgId>10005</MsgId>
        </xml>"""
        msg = WeChatProtocol.parse_message(xml)
        assert msg is not None
        assert msg["msg_type"] == "event"
        assert "subscribe" in msg["content"]


class TestMessageQueueIntegration:
    """MessageQueue 与 MCPHandler 集成测试。"""

    def test_queue_poll_then_handler_poll(self):
        """验证 queue poll 后被 handler poll 的行为。"""
        mq = MessageQueue()
        handler = MCPHandler(mq)

        mq.push("user_x", "text", "first message", "1")

        # 第一次 handler poll
        result1 = handler.handle("tools/call", {
            "name": "poll_messages",
            "arguments": {},
        })
        data1 = json.loads(result1["content"][0]["text"])
        assert len(data1) == 1  # user_x's message (cursor was 0)

        # 没有新消息，再次 poll
        result2 = handler.handle("tools/call", {
            "name": "poll_messages",
            "arguments": {},
        })
        data2 = json.loads(result2["content"][0]["text"])
        assert len(data2) == 0  # no new messages since last poll

    def test_get_server_status_reflects_queue(self):
        """get_server_status 反映队列状态。"""
        mq = MessageQueue()
        handler = MCPHandler(mq)

        result = handler.handle("tools/call", {
            "name": "get_server_status",
            "arguments": {},
        })
        data = json.loads(result["content"][0]["text"])
        assert data["queue_size"] == 0
        assert data["status"] == "running"

        mq.push("user_1", "text", "hello", "1")
        mq.push("user_2", "text", "world", "2")

        result = handler.handle("tools/call", {
            "name": "get_server_status",
            "arguments": {},
        })
        data = json.loads(result["content"][0]["text"])
        assert data["queue_size"] == 2
