"""检测用户的交互风格——决定关系从 trusted 分支到 brother/respected/crush。

在用户积累足够互动后，分析最近对话判断其风格。不是一次性判定，
而是随着对话持续 refine。
"""

from typing import Optional

from ..storage.models import User, RelationshipType

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
# 暧昧/焦虑信号词（南瓜视角）
ANXIOUS_EAGER_SIGNALS = [
    "想你", "在干嘛", "为什么不回", "有点想你",
    "睡不着", "陪我", "想你了", "你在哪",
]


class StyleDetector:
    """分析用户交互风格，推荐关系分支。"""

    def __init__(self):
        self._min_messages_for_detection = 30

    def detect(
        self, user: User, recent_messages: list[dict[str, str]]
    ) -> Optional[RelationshipType]:
        """返回推荐的关系类型，或 None（数据不足/无法判定）。"""
        if user.interaction_count < self._min_messages_for_detection:
            return None
        if user.relationship_type not in (
            RelationshipType.TRUSTED, RelationshipType.ACQUAINTANCE
        ):
            return None

        # 提取用户的所有 incoming 消息
        user_texts = [
            m["content"].lower()
            for m in recent_messages
            if m.get("role") == "user"
        ]
        if not user_texts:
            return None

        all_text = " ".join(user_texts)

        # 评分
        roast_score = sum(1 for s in MUTUAL_ROASTING_SIGNALS if s.lower() in all_text)
        care_score = sum(1 for s in CARE_GIVING_SIGNALS if s.lower() in all_text)
        eager_score = sum(1 for s in ANXIOUS_EAGER_SIGNALS if s.lower() in all_text)

        # 关系升降也需要时间——用户主动发起比例
        user_initiated_ratio = (
            user.user_initiated_count / max(user.interaction_count, 1)
        )

        # 深夜聊天比例
        late_night_ratio = user.late_night_count / max(user.interaction_count, 1)

        # 判定
        if roast_score >= 3 and user_initiated_ratio >= 0.3:
            return RelationshipType.BROTHER
        elif care_score >= 3 and roast_score < 2:
            return RelationshipType.RESPECTED
        elif eager_score >= 3 and late_night_ratio >= 0.2:
            return RelationshipType.CRUSH

        return None

    def get_layer4_rules(self, rel_type: RelationshipType) -> dict:
        """根据关系类型返回 Layer 4 的行为调整规则。"""
        rules = {
            RelationshipType.STRANGER: {
                "warmth": "礼貌但保持观察距离",
                "self_disclosure": "低——不主动暴露脆弱",
                "swearing": "几乎不说",
                "initiative": "偏被动",
            },
            RelationshipType.ACQUAINTANCE: {
                "warmth": "友好但不越界",
                "self_disclosure": "中低——偶尔分享日常",
                "swearing": "极少",
                "initiative": "中等",
            },
            RelationshipType.TRUSTED: {
                "warmth": "放松、真实",
                "self_disclosure": "中高——可以暴露脆弱面",
                "swearing": "中等",
                "initiative": "主动",
            },
            RelationshipType.BROTHER: {
                "warmth": "最放松——滚滚滚 + 爱你宝宝",
                "self_disclosure": "高——什么都可以说",
                "swearing": "最高",
                "initiative": "非常主动",
            },
            RelationshipType.RESPECTED: {
                "warmth": "克制但有深度",
                "self_disclosure": "中等——会求助、会感谢",
                "swearing": "极低",
                "initiative": "中等偏高",
            },
            RelationshipType.CRUSH: {
                "warmth": "外表放松但内在焦虑",
                "self_disclosure": "高——但容易过度",
                "swearing": "中等",
                "initiative": "高，容易用力过猛",
            },
        }
        return rules.get(rel_type, rules[RelationshipType.STRANGER])
