"""Estimate whether a user welcomes Nan Gua's life sharing."""

from .types import ReceptivityResult


class LifeReceptivity:
    """Rule-based receptivity estimator.

    The score is intentionally conservative. It is a nudge for context and
    proactive policy, not a relationship state replacement.
    """

    _POSITIVE_SIGNALS: dict[str, list[str]] = {
        "follow_up": ["后来呢", "然后呢", "怎么样了", "后续呢"],
        "care": ["你还好吗", "别太累", "休息一下", "照顾好自己"],
        "advice": ["你可以", "要不要试试", "我觉得你可以", "不如"],
        "banter": ["哈哈", "笑死", "你也这样", "太真实了"],
        "asks_about_ng": ["你今天干嘛", "你最近怎么样", "你呢", "你在干嘛"],
    }
    _NEGATIVE_SIGNALS: dict[str, list[str]] = {
        "explicit_refusal": ["不想听这个", "别说这个", "先说我的事"],
        "dismissive": ["哦", "嗯", "行吧", "随便"],
        "topic_shift": ["算了先不说这个", "换个话题", "说正事"],
    }

    @classmethod
    def estimate(cls, messages: list[dict[str, str]], window: int = 8) -> ReceptivityResult:
        user_messages = [
            m.get("content", "")
            for m in messages[-window:]
            if m.get("role") == "user"
        ]
        if not user_messages:
            return ReceptivityResult()

        positive: list[str] = []
        negative: list[str] = []
        score = 0.5

        for idx, text in enumerate(user_messages):
            recency_weight = 1.0 + (idx / max(len(user_messages), 1))
            for label, keywords in cls._POSITIVE_SIGNALS.items():
                if any(k in text for k in keywords):
                    if label not in positive:
                        positive.append(label)
                    score += 0.12 * recency_weight
            for label, keywords in cls._NEGATIVE_SIGNALS.items():
                if any(k in text for k in keywords):
                    if label not in negative:
                        negative.append(label)
                    score -= 0.18 * recency_weight

        score = round(max(0.0, min(1.0, score)), 2)
        if score >= 0.65:
            label = "high"
        elif score <= 0.4:
            label = "low"
        else:
            label = "neutral"

        return ReceptivityResult(
            score=score,
            label=label,
            positive_hits=positive,
            negative_hits=negative,
        )
