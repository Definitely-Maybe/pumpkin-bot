"""tests/test_contracts.py — 验证 5 个 dataclass 契约可实例化。"""

from src.core.contracts import (
    MessageContext, UserSession, PromptContext, LLMResponse, OutgoingBurst,
)
from src.storage.models import User, RelationshipType, PersonaState


def test_message_context_defaults():
    ctx = MessageContext(user_id="u1", raw_text="hello", timestamp="2026-06-14 22:00:00")
    assert ctx.platform == "terminal"
    assert ctx.user_id == "u1"
    assert ctx.raw_text == "hello"


def test_user_session_defaults():
    user = User(user_id="u1", platform="terminal", display_name="test")
    ps = PersonaState()
    session = UserSession(user=user, relationship=RelationshipType.STRANGER, persona_state=ps)
    assert session.history == []
    assert session.warm_summary is None
    assert session.cold_notes is None


def test_prompt_context_fields():
    pc = PromptContext(
        system_prompt="sp",
        messages=[{"role": "user", "content": "hi"}],
        sidecar_instruction="json please",
        fallback_data={"key": "value"},
    )
    assert pc.system_prompt == "sp"
    assert len(pc.messages) == 1


def test_llm_response_defaults():
    resp = LLMResponse(reply_text="hi", deep_topic=False, mood="neutral")
    assert resp.sidecar_parse_ok is True
    assert resp.tokens == 0
    assert resp.worth_remembering is None


def test_outgoing_burst():
    burst = OutgoingBurst(messages=["a", "b", "c"], delay_ms=600)
    assert len(burst.messages) == 3
    assert burst.delay_ms == 600
