"""tests/test_arcs.py"""
import random
import pytest
from src.social.arcs import ArcStateMachine, ArcType, ArcState


class TestStateMachine:
    def test_setup_to_rising(self):
        assert ArcStateMachine.can_transition(ArcState.SETUP, ArcState.RISING) is True

    def test_setup_to_dormant(self):
        assert ArcStateMachine.can_transition(ArcState.SETUP, ArcState.DORMANT) is True

    def test_setup_to_climax(self):
        # 不能跳级
        assert ArcStateMachine.can_transition(ArcState.SETUP, ArcState.CLIMAX) is False

    def test_rising_to_climax(self):
        assert ArcStateMachine.can_transition(ArcState.RISING, ArcState.CLIMAX) is True

    def test_rising_to_setup(self):
        # 反转：发展回酝酿
        assert ArcStateMachine.can_transition(ArcState.RISING, ArcState.SETUP) is True

    def test_rising_to_dormant(self):
        assert ArcStateMachine.can_transition(ArcState.RISING, ArcState.DORMANT) is True

    def test_climax_to_aftermath(self):
        assert ArcStateMachine.can_transition(ArcState.CLIMAX, ArcState.AFTERMATH) is True

    def test_climax_to_rising(self):
        # 连锁：一个高潮不够
        assert ArcStateMachine.can_transition(ArcState.CLIMAX, ArcState.RISING) is True

    def test_climax_to_dormant(self):
        # 戛然而止
        assert ArcStateMachine.can_transition(ArcState.CLIMAX, ArcState.DORMANT) is True

    def test_aftermath_to_dormant(self):
        assert ArcStateMachine.can_transition(ArcState.AFTERMATH, ArcState.DORMANT) is True

    def test_dormant_to_any(self):
        # 休眠不可逆
        for s in [ArcState.SETUP, ArcState.RISING, ArcState.CLIMAX, ArcState.AFTERMATH]:
            assert ArcStateMachine.can_transition(ArcState.DORMANT, s) is False

    def test_any_to_dormant(self):
        """任何非休眠阶段都可烂尾。"""
        for s in [ArcState.SETUP, ArcState.RISING, ArcState.CLIMAX, ArcState.AFTERMATH]:
            assert ArcStateMachine.can_transition(s, ArcState.DORMANT) is True


class TestArcTypeEventCount:
    def test_romance_range(self):
        for _ in range(30):
            n = ArcStateMachine.random_event_count("romance")
            assert 3 <= n <= 5

    def test_conflict_range(self):
        for _ in range(30):
            n = ArcStateMachine.random_event_count("conflict")
            assert 3 <= n <= 4

    def test_growth_range(self):
        for _ in range(30):
            n = ArcStateMachine.random_event_count("growth")
            assert 3 <= n <= 4

    def test_daily_range(self):
        for _ in range(30):
            n = ArcStateMachine.random_event_count("daily")
            assert 2 <= n <= 3


class TestAdvance:
    def test_advance_pushes_forward(self):
        """正常推进：SETUP → RISING。"""
        random.seed(42)
        new_state, is_dormant = ArcStateMachine.advance(ArcState.SETUP, force_dormant=False)
        assert new_state == ArcState.RISING
        assert is_dormant is False

    def test_advance_force_dormant(self):
        """强制休眠（烂尾/超时）。"""
        new_state, is_dormant = ArcStateMachine.advance(ArcState.RISING, force_dormant=True)
        assert new_state == ArcState.DORMANT
        assert is_dormant is True

    def test_advance_from_aftermath(self):
        """余波后 → 自动休眠。"""
        new_state, is_dormant = ArcStateMachine.advance(ArcState.AFTERMATH, force_dormant=False)
        assert new_state == ArcState.DORMANT
        assert is_dormant is True

    def test_advance_from_climax_random(self):
        """高潮 → 余波 或 发展 或 休眠。"""
        states_seen = set()
        for _ in range(50):
            new_state, _ = ArcStateMachine.advance(ArcState.CLIMAX, force_dormant=False)
            states_seen.add(new_state)
        # 至少看到 aftermath
        assert ArcState.AFTERMATH in states_seen
