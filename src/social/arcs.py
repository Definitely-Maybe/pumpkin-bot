"""叙事弧状态机——非线性，支持反转/烂尾/连锁。"""

import random
from enum import Enum


class ArcType(str, Enum):
    ROMANCE = "romance"
    CONFLICT = "conflict"
    GROWTH = "growth"
    DAILY = "daily"


class ArcState(str, Enum):
    SETUP = "setup"
    RISING = "rising"
    CLIMAX = "climax"
    AFTERMATH = "aftermath"
    DORMANT = "dormant"


class ArcStateMachine:
    """叙事弧状态机。"""

    # 状态转移表
    _TRANSITIONS: dict[ArcState, set[ArcState]] = {
        ArcState.SETUP:     {ArcState.RISING, ArcState.DORMANT},
        ArcState.RISING:    {ArcState.CLIMAX, ArcState.SETUP, ArcState.DORMANT},
        ArcState.CLIMAX:    {ArcState.AFTERMATH, ArcState.RISING, ArcState.DORMANT},
        ArcState.AFTERMATH: {ArcState.DORMANT},
        ArcState.DORMANT:   set(),  # 终点
    }

    # 弧类型 → 事件数范围 (min, max)
    _EVENT_COUNTS: dict[ArcType, tuple[int, int]] = {
        ArcType.ROMANCE: (3, 5),
        ArcType.CONFLICT: (3, 4),
        ArcType.GROWTH: (3, 4),
        ArcType.DAILY: (2, 3),
    }

    @classmethod
    def can_transition(cls, from_state: ArcState, to_state: ArcState) -> bool:
        """检查状态转移是否合法。"""
        return to_state in cls._TRANSITIONS.get(from_state, set())

    @classmethod
    def random_event_count(cls, arc_type: str) -> int:
        """根据弧类型返回随机事件数。"""
        rng = cls._EVENT_COUNTS.get(ArcType(arc_type), (2, 3))
        return random.randint(rng[0], rng[1])

    @classmethod
    def advance(cls, current: ArcState, force_dormant: bool = False) -> tuple[ArcState, bool]:
        """推进弧到下一阶段。

        Args:
            current: 当前弧状态
            force_dormant: 是否强制结束（烂尾/超时/事件数满）

        Returns:
            (new_state, is_dormant)
        """
        if force_dormant:
            return ArcState.DORMANT, True

        if current == ArcState.DORMANT:
            return ArcState.DORMANT, True

        # 余波后自动休眠
        if current == ArcState.AFTERMATH:
            return ArcState.DORMANT, True

        choices = list(cls._TRANSITIONS.get(current, set()))
        if not choices:
            return current, False

        # 按阶段加权选择
        if current == ArcState.SETUP:
            # 酝酿 → 发展（大概率）或 烂尾（小概率）
            weights = [0.85 if c == ArcState.RISING else 0.15 for c in choices]
            next_state = random.choices(choices, weights=weights, k=1)[0]
        elif current == ArcState.RISING:
            # 发展 → 高潮（70%）/ 反转回酝酿（20%）/ 烂尾（10%）
            wmap = {ArcState.CLIMAX: 0.70, ArcState.SETUP: 0.20, ArcState.DORMANT: 0.10}
            weights = [wmap[c] for c in choices]
            next_state = random.choices(choices, weights=weights, k=1)[0]
        elif current == ArcState.CLIMAX:
            weights = []
            for c in choices:
                if c == ArcState.AFTERMATH:
                    weights.append(0.6)
                elif c == ArcState.RISING:
                    weights.append(0.25)
                elif c == ArcState.DORMANT:
                    weights.append(0.15)
            next_state = random.choices(choices, weights=weights, k=1)[0]
        else:
            next_state = random.choice(choices)

        is_dormant = next_state == ArcState.DORMANT
        return next_state, is_dormant

    @classmethod
    def is_active(cls, state: ArcState) -> bool:
        """弧是否仍在活跃（非休眠）。"""
        return state != ArcState.DORMANT
