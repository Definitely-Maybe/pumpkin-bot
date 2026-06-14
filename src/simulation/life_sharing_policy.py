"""Policy for conservative life-event sharing decisions."""

import json
from dataclasses import dataclass
from typing import Optional

from ..storage.models import RelationshipType, TriggerType, User
from .life_context_selector import LifeContextSelector
from .types import ReceptivityResult, ShareLevel


@dataclass
class LifeShareDecision:
    should_share: bool
    event: Optional[dict] = None
    reason: str = "not_allowed"
    instruction: str = ""
    trigger_type: Optional[TriggerType] = None
    share_level: Optional[ShareLevel] = None
    score: float = 0.0


class LifeSharingPolicy:
    """Choose at most one event that is worth a proactive life share."""

    _DISTRESS_WORDS = ["崩溃", "难受", "痛苦", "不想活", "怎么办", "撑不住"]
    _EXPLICIT_ASK_WORDS = [
        "你今天干嘛",
        "你今天做了什么",
        "你最近怎么样",
        "最近怎么样",
        "你在干嘛",
        "南瓜你",
        "你的近况",
    ]
    _PROACTIVE_RELATIONSHIPS = {
        RelationshipType.TRUSTED,
        RelationshipType.BROTHER,
        RelationshipType.RESPECTED,
        RelationshipType.CRUSH,
    }
    _ALLOWED_LEVELS: dict[RelationshipType, set[ShareLevel]] = {
        RelationshipType.STRANGER: {ShareLevel.PUBLIC},
        RelationshipType.ACQUAINTANCE: {ShareLevel.PUBLIC},
        RelationshipType.TRUSTED: {ShareLevel.PUBLIC, ShareLevel.CASUAL, ShareLevel.PERSONAL},
        RelationshipType.BROTHER: {ShareLevel.PUBLIC, ShareLevel.CASUAL, ShareLevel.PERSONAL},
        RelationshipType.RESPECTED: {
            ShareLevel.PUBLIC,
            ShareLevel.CASUAL,
            ShareLevel.PERSONAL,
            ShareLevel.VULNERABLE,
        },
        RelationshipType.CRUSH: {
            ShareLevel.PUBLIC,
            ShareLevel.CASUAL,
            ShareLevel.PERSONAL,
            ShareLevel.VULNERABLE,
        },
    }

    def select_event(
        self,
        user: User,
        user_message: str,
        events: list[dict],
        receptivity: ReceptivityResult,
        life_shares_today: int,
    ) -> LifeShareDecision:
        explicit_ask = self._is_explicit_ask(user_message)
        if self._strong_distress(user_message):
            return LifeShareDecision(False, reason="user_distress")
        if receptivity.label == "low":
            return LifeShareDecision(False, reason="low_receptivity")
        if not explicit_ask and life_shares_today >= 1:
            return LifeShareDecision(False, reason="daily_limit_reached")
        if not explicit_ask and user.relationship_type not in self._PROACTIVE_RELATIONSHIPS:
            return LifeShareDecision(False, reason="relationship_not_ready")

        candidates = [
            self._candidate(user, event, receptivity, explicit_ask)
            for event in events
            if not self._is_shared(event, user.user_id)
        ]
        candidates = [candidate for candidate in candidates if candidate is not None]
        if not candidates:
            return LifeShareDecision(False, reason="no_shareable_events")

        best = max(candidates, key=lambda candidate: candidate.score)
        threshold = 0.2 if explicit_ask else 0.62
        if best.score < threshold:
            return LifeShareDecision(False, reason="no_event_scored_high_enough")

        return LifeShareDecision(
            should_share=True,
            event=best.event,
            reason="explicit_user_ask" if explicit_ask else "proactive_high_value_event",
            instruction=self._format_instruction(best.event, explicit_ask),
            trigger_type=(
                TriggerType.SOCIAL_SHARE
                if best.event.get("event_type") == "social"
                else TriggerType.LIFE_STORY
            ),
            share_level=best.share_level,
            score=best.score,
        )

    @dataclass
    class _Candidate:
        event: dict
        share_level: ShareLevel
        score: float

    def _candidate(
        self,
        user: User,
        event: dict,
        receptivity: ReceptivityResult,
        explicit_ask: bool,
    ) -> Optional[_Candidate]:
        share_level = LifeContextSelector.classify_share_level(event)
        allowed = self._ALLOWED_LEVELS.get(user.relationship_type, {ShareLevel.PUBLIC})
        if share_level not in allowed:
            return None
        if user.relationship_type == RelationshipType.STRANGER and share_level != ShareLevel.PUBLIC:
            return None
        if user.relationship_type == RelationshipType.STRANGER and event.get("category") == "creative":
            return None

        score = self.score_event(user, event, receptivity, explicit_ask, share_level)
        return self._Candidate(event=event, share_level=share_level, score=score)

    @classmethod
    def score_event(
        cls,
        user: User,
        event: dict,
        receptivity: ReceptivityResult,
        explicit_ask: bool,
        share_level: Optional[ShareLevel] = None,
    ) -> float:
        category = event.get("category", "")
        event_type = event.get("event_type", "")
        description = event.get("description", "")
        level = share_level or LifeContextSelector.classify_share_level(event)

        score = receptivity.score * 0.25
        if explicit_ask:
            score += 0.2
        if user.relationship_type in cls._PROACTIVE_RELATIONSHIPS:
            score += 0.08
        if event_type == "social":
            score += 0.18
        if category == "body_state":
            score += 0.28
        elif category == "reflection":
            score += 0.24
        elif category == "creative":
            score += 0.18
        elif category == "daily":
            score += 0.12
        if level in {ShareLevel.PERSONAL, ShareLevel.VULNERABLE}:
            score += 0.16
        if event.get("causality_chain_id"):
            score += 0.12
        if any(word in description for word in ["低电量", "想明白", "好笑", "卡住", "后续"]):
            score += 0.18

        return round(min(1.0, score), 2)

    @classmethod
    def _format_instruction(cls, event: dict, explicit_ask: bool) -> str:
        opening = (
            "用户明确问到南瓜近况，可以简短回答；"
            if explicit_ask
            else "这是一条可主动分享的南瓜近况素材；"
        )
        return (
            f"{opening}如果不自然就不要提。必须短、轻、克制，不要像日报，"
            "不要解释系统记录，不要变成南瓜独白，提到后要回到用户。"
            f"近况：{event.get('description', '')}"
        )

    @classmethod
    def _strong_distress(cls, text: str) -> bool:
        return any(word in text for word in cls._DISTRESS_WORDS)

    @classmethod
    def _is_explicit_ask(cls, text: str) -> bool:
        return any(word in text for word in cls._EXPLICIT_ASK_WORDS)

    @staticmethod
    def _is_shared(event: dict, user_id: str) -> bool:
        raw = event.get("shared_with_users") or "[]"
        try:
            shared = json.loads(raw)
        except json.JSONDecodeError:
            return False
        return user_id in shared
