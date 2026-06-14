"""分支检测 + 漂移逻辑。替代 style_detector.py。

规则优先 + LLM 兜底：规则覆盖 80% 场景（零成本），边界 case 委托 LLM。
"""

from typing import Optional

from ..storage.models import RelationshipType

# 互损风格信号词
MUTUAL_ROASTING_SIGNALS = [
    "滚滚滚", "滚吧", "傻逼", "你他妈", "你tm",
    "逆天", "抽象", "神人", "憨批", "菜逼",
]
# 关心/建议风格信号词
CARE_GIVING_SIGNALS = [
    "你还好吗", "还好吗", "你最近怎么样", "照顾好自己",
    "你要不要", "你该", "你试试", "我觉得你可以",
    "你别", "你不要", "别太", "注意",
]
# 暧昧/焦虑信号词（用户视角）
ANXIOUS_EAGER_SIGNALS = [
    "想你", "在干嘛", "为什么不回", "有点想你",
    "睡不着", "陪我", "想你了", "你在哪",
]


def _score_signals(
    recent_user_messages: list[str],
) -> dict[str, int]:
    """计算三类信号分（不判分支，纯统计）。"""
    all_text = " ".join(m.lower() for m in recent_user_messages)
    return {
        "roast": sum(1 for s in MUTUAL_ROASTING_SIGNALS if s.lower() in all_text),
        "care": sum(1 for s in CARE_GIVING_SIGNALS if s.lower() in all_text),
        "eager": sum(1 for s in ANXIOUS_EAGER_SIGNALS if s.lower() in all_text),
    }


def detect_branch_signals(
    recent_user_messages: list[str],
    late_night_ratio: float = 0.0,
    initiative_ratio: float = 0.0,
) -> Optional[RelationshipType]:
    """根据最近用户消息 + 统计信号检测分支方向。

    Returns: RelationshipType (brother/respected/crush) 或 None
    """
    scores = _score_signals(recent_user_messages)
    roast_score = scores["roast"]
    care_score = scores["care"]
    eager_score = scores["eager"]

    if roast_score >= 3 and initiative_ratio >= 0.3:
        return RelationshipType.BROTHER
    elif care_score >= 3 and roast_score < 2:
        return RelationshipType.RESPECTED
    elif eager_score >= 3 and late_night_ratio >= 0.2:
        return RelationshipType.CRUSH

    return None


def is_boundary(
    recent_user_messages: list[str],
    late_night_ratio: float = 0.0,
    initiative_ratio: float = 0.0,
) -> bool:
    """判断当前信号是否处于边界（应委托 LLM）。

    边界条件（任一满足即为边界）：
    1. 某信号分 == 2（差 1 分触发）
    2. 两个分支同时各命中 ≥2（互斥不了）
    3. 信号分够了但辅助条件不够（如 eager≥3 但 late_night < 0.2）
    """
    scores = _score_signals(recent_user_messages)
    r, c, e = scores["roast"], scores["care"], scores["eager"]

    # 条件 1：差 1 分触发
    if r == 2 or c == 2 or e == 2:
        return True

    # 条件 2：两个分支同时活跃
    active = sum(1 for s in (r, c, e) if s >= 2)
    if active >= 2:
        return True

    # 条件 3：信号够了但辅助条件不够
    if r >= 3 and initiative_ratio < 0.3:
        return True
    if e >= 3 and late_night_ratio < 0.2:
        return True

    return False


def update_streak(current_streak: int, signal_match: bool) -> int:
    """更新分支信号 streak 计数器。

    - 匹配：streak + 1（上限 30）
    - 不匹配：
      - streak > 0 → 重置为 -1
      - streak ≤ 0 → streak - 1（下限 -30）
    """
    if signal_match:
        return min(current_streak + 1, 30)
    else:
        if current_streak > 0:
            return -1
        else:
            return max(current_streak - 1, -30)


def should_activate_branch(
    streak: int, current_branch: Optional[RelationshipType],
) -> bool:
    """判断是否应切入分支。"""
    return streak >= 5 and current_branch is None


def should_retreat_branch(
    streak: int, current_branch: Optional[RelationshipType],
) -> bool:
    """判断是否应回退分支到 trusted。"""
    return streak <= -10 and current_branch is not None


class BranchDetector:
    """分支检测器——封装检测 + streak 管理。

    规则优先 + LLM 兜底：detect() 只跑规则（同步），
    detect_with_fallback() 在边界 case 委托 LLM（异步）。
    """

    def __init__(self, llm=None):
        self._min_messages_for_detection = 30
        self.llm = llm

    def detect(
        self,
        recent_messages: list[dict[str, str]],
        interaction_count: int,
        late_night_count: int,
        user_initiated_count: int,
        current_relationship: RelationshipType,
    ) -> Optional[RelationshipType]:
        """纯规则检测（同步），零成本。"""

        # 只在 trusted 阶段触发分支检测
        if current_relationship != RelationshipType.TRUSTED:
            return None

        # 数据不足
        if interaction_count < self._min_messages_for_detection:
            return None

        user_texts = [
            m["content"]
            for m in recent_messages
            if m.get("role") == "user"
        ]
        if not user_texts:
            return None

        late_night_ratio = late_night_count / max(interaction_count, 1)
        initiative_ratio = user_initiated_count / max(interaction_count, 1)

        return detect_branch_signals(
            user_texts,
            late_night_ratio=late_night_ratio,
            initiative_ratio=initiative_ratio,
        )

    async def detect_with_fallback(
        self,
        recent_messages: list[dict[str, str]],
        interaction_count: int,
        late_night_count: int,
        user_initiated_count: int,
        current_relationship: RelationshipType,
        system_prompt: str = "",
    ) -> Optional[RelationshipType]:
        """规则优先 + LLM 兜底（异步）。

        规则命中 → 直接返回；边界 case → LLM 分类。
        用于 sidecar 异步阶段，不影响当前轮回复。
        """
        # 只在 trusted 阶段触发
        if current_relationship != RelationshipType.TRUSTED:
            return None

        # 数据不足
        if interaction_count < self._min_messages_for_detection:
            return None

        user_texts = [
            m["content"]
            for m in recent_messages
            if m.get("role") == "user"
        ]
        if not user_texts:
            return None

        late_night_ratio = late_night_count / max(interaction_count, 1)
        initiative_ratio = user_initiated_count / max(interaction_count, 1)

        # 1. 规则检测
        rule_result = detect_branch_signals(
            user_texts, late_night_ratio, initiative_ratio,
        )

        # 2. 规则结果明确 → 直接返回
        if rule_result is not None and not is_boundary(
            user_texts, late_night_ratio, initiative_ratio,
        ):
            return rule_result

        # 3. 边界 case → LLM 兜底
        if self.llm:
            llm_result = await self.llm.classify_branch(
                user_texts, system_prompt,
            )
            if llm_result is not None:
                return llm_result

        # 4. LLM 不可用或失败 → 回退到规则结果
        return rule_result
