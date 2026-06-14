"""tests/test_social_integration.py — 社交模拟集成测试。不需要 API key。"""
import json
import pytest
from src.social.arcs import ArcStateMachine, ArcState, ArcType
from src.storage.models import SocialCharacter, SocialArc


def test_full_arc_lifecycle():
    """完整弧生命周期：酝酿→发展→高潮→余波→休眠。"""
    arc = SocialArc(
        arc_id="test-arc-1",
        character_id="test-char",
        arc_type="romance",
        status=ArcState.SETUP,
        max_events=4,
    )

    # Setup → Rising (should normally advance)
    s, done = ArcStateMachine.advance(arc.status, force_dormant=False)
    assert not done
    arc.status = s
    # Rising → Climax or SETUP (反转)
    s, done = ArcStateMachine.advance(arc.status, force_dormant=False)
    arc.status = s
    # If we got to CLIMAX, advance more
    if arc.status == ArcState.CLIMAX:
        s, done = ArcStateMachine.advance(arc.status, force_dormant=False)
        arc.status = s
    # Eventually should reach DORMANT if we max out events
    if arc.status == ArcState.AFTERMATH:
        s, done = ArcStateMachine.advance(arc.status, force_dormant=False)
        assert s == ArcState.DORMANT and done


def test_forced_dormant_from_any_state():
    """任何活跃阶段可被强制休眠。"""
    for state in [ArcState.SETUP, ArcState.RISING, ArcState.CLIMAX, ArcState.AFTERMATH]:
        s, done = ArcStateMachine.advance(state, force_dormant=True)
        assert s == ArcState.DORMANT
        assert done is True


def test_setup_advance_does_not_randomly_end_before_story_starts(monkeypatch):
    """酝酿阶段的第一步不能随机烂尾，否则生命周期测试会偶发失败。"""
    monkeypatch.setattr(
        "src.social.arcs.random.choices",
        lambda choices, weights, k: [ArcState.DORMANT],
    )

    s, done = ArcStateMachine.advance(ArcState.SETUP, force_dormant=False)

    assert s == ArcState.RISING
    assert done is False


def test_romance_arc_has_min_events():
    """浪漫弧至少 3 个事件。"""
    for _ in range(20):
        n = ArcStateMachine.random_event_count("romance")
        assert 3 <= n <= 5


def test_no_transition_from_climax_to_setup():
    """高潮不可直接跳回酝酿——只能通过发展。"""
    assert ArcStateMachine.can_transition(ArcState.CLIMAX, ArcState.SETUP) is False


def test_self_md_characters_have_required_fields():
    """验证 self.md 角色数据完整性。"""
    from src.social.characters import CharacterManager
    chars = CharacterManager._load_self_md_characters()
    assert len(chars) >= 4
    for c in chars:
        assert c.character_id
        assert c.name
        traits = json.loads(c.traits)
        assert len(traits) >= 3
        assert c.core_tension, f"{c.name} 缺少 core_tension"
        arc_types = json.loads(c.allowed_arc_types)
        assert len(arc_types) >= 1, f"{c.name} 缺少 allowed_arc_types"
