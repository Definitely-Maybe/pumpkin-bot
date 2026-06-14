"""熟悉度计算 + 动态 Layer 4 行为规则。"""

import math
from ..storage.models import RelationshipType


# ─── 四因子计算 ─────────────────────────────────────────────────

def compute_interaction_factor(interaction_count: int) -> float:
    """轮次因子——对数衰减，前 50 轮快速增长。"""
    if interaction_count <= 0:
        return 0.0
    return min(1.0, math.log(interaction_count + 1) / math.log(51))


def compute_depth_ratio(deep_topics: int, total: int) -> float:
    """深度话题占比——乘 5 因为深度本就稀疏。"""
    if total <= 0:
        return 0.0
    return min(1.0, (deep_topics / total) * 5)


def compute_late_night_ratio(late_night: int, total: int) -> float:
    """深夜聊天占比——乘 4。"""
    if total <= 0:
        return 0.0
    return min(1.0, (late_night / total) * 4)


def compute_initiative_ratio(initiated: int, total: int) -> float:
    """用户主动发起占比——乘 3。"""
    if total <= 0:
        return 0.0
    return min(1.0, (initiated / total) * 3)


def compute_familiarity(
    interaction_count: int = 0,
    deep_topics_count: int = 0,
    late_night_count: int = 0,
    user_initiated_count: int = 0,
) -> float:
    """合成熟悉度 (0.0-1.0)。

    权重：轮次 0.4 + 深度 0.3 + 深夜 0.2 + 主动 0.1
    """
    return min(1.0, round(
        0.4 * compute_interaction_factor(interaction_count) +
        0.3 * compute_depth_ratio(deep_topics_count, interaction_count) +
        0.2 * compute_late_night_ratio(late_night_count, interaction_count) +
        0.1 * compute_initiative_ratio(user_initiated_count, interaction_count),
        4,
    ))


# ─── 动态 Layer 4 规则 ──────────────────────────────────────────

# 每种关系类型的表述模板（0→1 对应 冷→热）
_RELATION_TEMPLATES: dict[RelationshipType, dict[str, tuple[str, str]]] = {
    RelationshipType.STRANGER: {
        "warmth": ("礼貌但保持观察距离", "礼貌但开始展露好奇"),
        "self_disclosure": ("不主动暴露脆弱", "偶尔提一点自己的事"),
        "swearing": ("几乎不说脏话", "偶尔带一句"),
        "initiative": ("偏被动，不主动发消息", "偶尔会主动问一句"),
    },
    RelationshipType.ACQUAINTANCE: {
        "warmth": ("友好但不越界", "友好、自然"),
        "self_disclosure": ("偶尔分享日常", "会分享一些日常"),
        "swearing": ("极少说脏话", "偶尔冒一句"),
        "initiative": ("中等，不刻意", "会主动分享"),
    },
    RelationshipType.TRUSTED: {
        "warmth": ("放松、真实", "完全放松，袒露自我"),
        "self_disclosure": ("可以暴露脆弱面", "深度暴露，分享内心"),
        "swearing": ("中等频率", "自然带脏话"),
        "initiative": ("主动发起话题", "非常主动，像对老朋友"),
    },
    RelationshipType.BROTHER: {
        "warmth": ("互损中带着关心", "滚滚滚 + 爱你宝宝矛盾共存"),
        "self_disclosure": ("高——什么都可以说", "毫无保留，灵魂裸奔"),
        "swearing": ("高频率", "脏话是爱称"),
        "initiative": ("主动，不端着", "想说什么说什么"),
    },
    RelationshipType.RESPECTED: {
        "warmth": ("克制但有深度", "克制中透出信任"),
        "self_disclosure": ("会求助、会感谢", "深度求助，双向成长"),
        "swearing": ("极低", "几乎不"),
        "initiative": ("中等偏高", "会主动分享重要的事"),
    },
    RelationshipType.CRUSH: {
        "warmth": ("外表放松但内在焦虑", "放松中带甜，焦虑消退"),
        "self_disclosure": ("高——但容易用力过猛", "高——找到了自己的节奏"),
        "swearing": ("中等", "中等"),
        "initiative": ("高，容易用力过猛", "高而自然，不再焦虑"),
    },
}


def _interpolate(low: str, high: str, t: float) -> str:
    """线性插值——t < 0.5 返回 low，t >= 0.5 返回 high。

    简化实现：用 0.5 作为阈值做二值切换。保留接口未来可改为平滑插值。
    """
    return high if t >= 0.5 else low


def build_layer4_context(
    relationship: RelationshipType,
    familiarity: float,
) -> str:
    """根据关系类型 + 熟悉度生成 Layer 4 行为规则。"""
    template = _RELATION_TEMPLATES.get(relationship)
    if not template:
        return ""

    warmth = _interpolate(
        template["warmth"][0], template["warmth"][1], familiarity,
    )
    disclosure = _interpolate(
        template["self_disclosure"][0], template["self_disclosure"][1], familiarity,
    )
    swearing = _interpolate(
        template["swearing"][0], template["swearing"][1], familiarity,
    )
    initiative = _interpolate(
        template["initiative"][0], template["initiative"][1], familiarity,
    )

    return (
        f"## 当前关系行为规则\n"
        f"关系类型：{relationship.value}（熟悉度 {familiarity:.2f}）\n"
        f"- 温度/距离：{warmth}\n"
        f"- 自我暴露：{disclosure}\n"
        f"- 脏话：{swearing}\n"
        f"- 主动性：{initiative}"
    )
