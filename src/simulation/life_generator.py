"""Generate low-key non-social life events without calling an LLM."""

import random
from datetime import datetime

from ..storage.models import LifeEvent


class LifeGenerator:
    """MVP template generator for Nan Gua daily life traces."""

    _DAY_WEIGHTS = [
        ("daily", 60),
        ("creative", 12),
        ("body_state", 15),
        ("reflection", 8),
    ]
    _NIGHT_WEIGHTS = [
        ("daily", 35),
        ("creative", 8),
        ("body_state", 32),
        ("reflection", 25),
    ]
    _TEMPLATES: dict[str, list[tuple[str, str]]] = {
        "daily": [
            ("下午出门买水，路上有点放空，回来才发现自己走得很慢。", "calm"),
            ("吃饭的时候刷了会儿手机，没刷到什么有意思的，倒是把时间刷没了。", "neutral"),
            ("本来想收拾一下桌子，结果只把杯子挪了个位置。", "neutral"),
            ("路过楼下的时候吹了会儿风，脑子稍微清醒了一点。", "calm"),
        ],
        "creative": [
            ("写东西写到一半卡住了，后来只记下一句很粗糙的想法。", "focused"),
            ("看着项目文件发了会儿呆，突然觉得有个小结构可以拆得更干净。", "focused"),
            ("本来想推进一点 bot 的逻辑，结果先被一个命名问题绊住了。", "neutral"),
        ],
        "body_state": [
            ("下午有点低电量，坐着放空了十分钟。", "tired"),
            ("昨晚睡得不算踏实，今天反应慢半拍。", "tired"),
            ("晚一点的时候整个人缓过来了一点，没有下午那么钝。", "calm"),
        ],
        "reflection": [
            ("深夜的时候突然想起自己最近有点用力过猛，心里安静了一会儿。", "reflective"),
            ("洗完澡后脑子松下来，意识到有些事不用立刻想明白。", "reflective"),
            ("晚上有一小段时间很想逃开消息，但后来又觉得这不算坏事。", "reflective"),
        ],
    }

    def __init__(self, rng: random.Random | None = None):
        self.rng = rng or random.Random()

    def generate(self, now: datetime | None = None, reason: str = "regular") -> LifeEvent:
        now = now or datetime.now()
        category = self._choose_category(now)
        description, emotion = self.rng.choice(self._TEMPLATES[category])
        if reason == "catchup":
            description = self._soften_for_catchup(description)
        return LifeEvent(
            event_type="life",
            category=category,
            description=description,
            characters_involved="[]",
            emotion=emotion,
            causality_chain_id=None,
            created_at=now.strftime("%Y-%m-%d %H:%M:%S"),
        )

    def _choose_category(self, now: datetime) -> str:
        weights = self._NIGHT_WEIGHTS if now.hour >= 22 or now.hour <= 2 else self._DAY_WEIGHTS
        categories = [c for c, _ in weights]
        values = [w for _, w in weights]
        return self.rng.choices(categories, weights=values, k=1)[0]

    @staticmethod
    def _soften_for_catchup(description: str) -> str:
        replacements = {
            "下午": "前阵子有一会儿",
            "晚一点的时候": "后来某个时候",
            "昨晚": "有天晚上",
            "深夜的时候": "有天深夜",
        }
        for old, new in replacements.items():
            description = description.replace(old, new)
        return description
