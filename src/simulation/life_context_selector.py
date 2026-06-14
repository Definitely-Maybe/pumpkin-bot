"""Select one existing life event that may be naturally mentioned in prompt."""

import json

from ..storage.models import RelationshipType, User
from .types import LifeContextCandidate, ReceptivityResult, ShareLevel


class LifeContextSelector:
    """Choose at most one life event for optional prompt injection."""

    _DISTRESS_WORDS = ["崩溃", "难受", "痛苦", "不想活", "怎么办", "撑不住"]
    _TOPIC_KEYWORDS: dict[str, list[str]] = {
        "body_state": ["累", "困", "没电", "低电量", "熬夜", "睡"],
        "creative": ["代码", "项目", "prompt", "bot", "卡住", "灵感"],
        "reflection": ["想法", "反思", "焦虑", "自我", "深夜"],
        "daily": ["吃", "出门", "散步", "天气", "上课", "日常"],
        "social": ["朋友", "同学", "wtt", "ccx", "mxt", "mcyy", "颜姐"],
    }
    _RELATION_ALLOWED_LEVELS: dict[RelationshipType, set[ShareLevel]] = {
        RelationshipType.STRANGER: {ShareLevel.PUBLIC},
        RelationshipType.ACQUAINTANCE: {ShareLevel.PUBLIC, ShareLevel.CASUAL},
        RelationshipType.TRUSTED: {ShareLevel.PUBLIC, ShareLevel.CASUAL, ShareLevel.PERSONAL},
        RelationshipType.BROTHER: {ShareLevel.PUBLIC, ShareLevel.CASUAL, ShareLevel.PERSONAL},
        RelationshipType.RESPECTED: {ShareLevel.PUBLIC, ShareLevel.CASUAL, ShareLevel.PERSONAL, ShareLevel.VULNERABLE},
        RelationshipType.CRUSH: {ShareLevel.PUBLIC, ShareLevel.CASUAL, ShareLevel.PERSONAL, ShareLevel.VULNERABLE},
    }

    def select(
        self,
        user: User,
        user_message: str,
        events: list[dict],
        receptivity: ReceptivityResult,
    ) -> LifeContextCandidate | None:
        if not events:
            return None
        if self._strong_distress(user_message):
            return None
        if receptivity.label == "low":
            return None

        best: LifeContextCandidate | None = None
        for event in events:
            if self._is_shared(event, user.user_id):
                continue
            share_level = self.classify_share_level(event)
            allowed = self._RELATION_ALLOWED_LEVELS.get(user.relationship_type, {ShareLevel.PUBLIC})
            if share_level not in allowed:
                continue
            score = self._score_event(user_message, event, receptivity)
            if score < 0.45:
                continue
            candidate = LifeContextCandidate(
                event_id=event.get("event_id"),
                description=event.get("description", ""),
                category=event.get("category", ""),
                event_type=event.get("event_type", ""),
                share_level=share_level,
                score=score,
            )
            if best is None or candidate.score > best.score:
                best = candidate
        return best

    def format_for_prompt(self, candidate: LifeContextCandidate | None) -> str:
        if candidate is None:
            return ""
        return (
            "## 南瓜最近可联想到的一件生活小事\n"
            f"- {candidate.description}\n\n"
            "如果自然相关，可以像朋友顺手一提；如果不贴合当前话题，就完全不要提。\n"
            "不要解释这是记忆、事件或系统记录。\n"
            "提到后要回到用户，不要展开成南瓜独白。"
        )

    @classmethod
    def classify_share_level(cls, event: dict) -> ShareLevel:
        category = event.get("category", "")
        description = event.get("description", "")
        if category == "reflection":
            return ShareLevel.VULNERABLE
        if category == "body_state" or any(w in description for w in ["低电量", "焦虑", "自我怀疑"]):
            return ShareLevel.PERSONAL
        if category in ("creative", "social"):
            return ShareLevel.CASUAL
        return ShareLevel.PUBLIC

    @classmethod
    def _strong_distress(cls, text: str) -> bool:
        return any(word in text for word in cls._DISTRESS_WORDS)

    @classmethod
    def _is_shared(cls, event: dict, user_id: str) -> bool:
        raw = event.get("shared_with_users") or "[]"
        try:
            shared = json.loads(raw)
        except json.JSONDecodeError:
            return False
        return user_id in shared

    @classmethod
    def _score_event(cls, user_message: str, event: dict, receptivity: ReceptivityResult) -> float:
        category = event.get("category", "")
        description = event.get("description", "")
        score = 0.15 + (receptivity.score * 0.25)

        for keyword in cls._TOPIC_KEYWORDS.get(category, []):
            if keyword.lower() in user_message.lower() or keyword.lower() in description.lower():
                score += 0.2

        for keyword in ["累", "困", "没电", "低电量"]:
            if keyword in user_message and keyword in description:
                score += 0.25

        if "?" in user_message or "？" in user_message or "你最近" in user_message or "你今天" in user_message:
            score += 0.15

        return round(min(1.0, score), 2)
