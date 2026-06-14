"""Small value types for Nan Gua life simulation."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class LifeEventKind(str, Enum):
    DAILY = "daily"
    CREATIVE = "creative"
    BODY_STATE = "body_state"
    REFLECTION = "reflection"
    SOCIAL = "social"


class ShareLevel(str, Enum):
    PUBLIC = "public"
    CASUAL = "casual"
    PERSONAL = "personal"
    VULNERABLE = "vulnerable"


@dataclass
class ReceptivityResult:
    score: float = 0.5
    label: str = "neutral"
    positive_hits: list[str] = field(default_factory=list)
    negative_hits: list[str] = field(default_factory=list)


@dataclass
class CatchupDecision:
    due: bool
    count: int = 0
    reason: str = "not_due"


@dataclass
class LifeContextCandidate:
    event_id: Optional[int]
    description: str
    category: str
    event_type: str
    share_level: ShareLevel
    score: float
