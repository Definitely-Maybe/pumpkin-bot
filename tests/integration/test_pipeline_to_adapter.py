"""tests/integration/test_pipeline_to_adapter.py

场景 2: Pipeline → Adapter
验证链：MessageBus.on_message() → 4 阶段 pipeline → adapter.send() 走对平台。
"""
import pytest
from unittest.mock import AsyncMock, patch

from src.core.pipeline import MessageBus
from src.gateway.terminal_adapter import TerminalAdapter
from src.gateway.wechat_adapter import WeChatAdapter
from src.gateway.mcp_client import MCPHttpClient


@pytest.mark.llm
@pytest.mark.asyncio
async def test_pipeline_routes_to_terminal_adapter(
    db, llm, session_mgr, context_asm, postprocessor, make_user, insert_message,
):
    """terminal-user 发消息 → TerminalAdapter.send() 被调用。"""
    await make_user(
        user_id="terminal-user", platform="terminal",
        relationship_type="trusted", interaction_count=30,
    )

    term = TerminalAdapter(bot_name="test")
    sent_messages = []
    original_send = term.send

    async def spy_send(user_id, messages):
        sent_messages.append((user_id, messages))
        await original_send(user_id, messages)
    term.send = spy_send

    bus = MessageBus(db, session_mgr, context_asm, llm, postprocessor, adapters=[term])
    await bus.on_message("terminal-user", "你好呀南瓜")

    assert len(sent_messages) == 1
    user_id, msgs = sent_messages[0]
    assert user_id == "terminal-user"
    assert len(msgs) >= 1
    assert any(len(m.strip()) > 0 for m in msgs)


@pytest.mark.llm
@pytest.mark.asyncio
async def test_pipeline_routes_to_wechat_adapter(
    db, llm, session_mgr, context_asm, postprocessor, make_user, insert_message,
):
    """openid 用户发消息 → WeChatAdapter.send() → MCPClient.call("send_message")。"""
    await make_user(
        user_id="openid_test_001", platform="wechat",
        relationship_type="stranger", interaction_count=5,
    )

    mock_mcp = AsyncMock(spec=MCPHttpClient)
    mock_mcp.call = AsyncMock(return_value={"success": True})
    mock_mcp.initialize = AsyncMock(return_value=True)

    wechat = WeChatAdapter(mock_mcp)
    term = TerminalAdapter(bot_name="test")

    bus = MessageBus(db, session_mgr, context_asm, llm, postprocessor,
                     adapters=[term, wechat])
    await bus.on_message("openid_test_001", "你好")

    send_calls = [c for c in mock_mcp.call.call_args_list
                  if c[0][0] == "send_message"]
    assert len(send_calls) >= 1
    assert send_calls[0][0][1]["user_openid"] == "openid_test_001"


@pytest.mark.asyncio
async def test_two_adapters_no_cross_routing():
    """两个 adapter 同时在线，消息路由互不串。"""
    term = TerminalAdapter.__new__(TerminalAdapter)
    term.platform = "terminal"
    term._running = False
    term.bot_name = "test"

    wechat = WeChatAdapter.__new__(WeChatAdapter)
    wechat.platform = "wechat"
    wechat._running = False

    bus = MessageBus.__new__(MessageBus)
    bus.adapters = [term, wechat]

    found = bus._find_adapter("terminal-user")
    assert found is not None
    assert found.platform == "terminal"

    found = bus._find_adapter("openid_someone")
    assert found is not None
    assert found.platform == "wechat"
