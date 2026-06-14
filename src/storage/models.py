"""数据模型 — 所有 dataclass 定义，无外部依赖。"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class RelationshipType(str, Enum):
    STRANGER = "stranger"
    ACQUAINTANCE = "acquaintance"
    TRUSTED = "trusted"
    BROTHER = "brother"
    RESPECTED = "respected"
    CRUSH = "crush"


class Direction(str, Enum):
    INCOMING = "incoming"
    OUTGOING = "outgoing"


class TriggerType(str, Enum):
    INACTIVITY = "inactivity"
    TIME_OF_DAY = "time_of_day"
    MILESTONE = "milestone"
    MEMORY_TRIGGER = "memory_trigger"
    SOCIAL_SHARE = "social_share"
    LIFE_STORY = "life_story"


@dataclass
class User:
    user_id: str
    platform: str
    display_name: Optional[str] = None
    relationship_type: RelationshipType = RelationshipType.STRANGER
    familiarity_score: float = 0.0
    branch_signal_streak: int = 0       # 分支信号连续满足/不满足的轮数
    branch_type: Optional[str] = None   # 当前分支方向（brother/respected/crush/null）
    interaction_count: int = 0
    deep_topics_count: int = 0
    user_initiated_count: int = 0
    late_night_count: int = 0
    corrections_count: int = 0
    first_interaction: Optional[str] = None
    last_interaction: Optional[str] = None
    topics_discussed: str = "[]"       # JSON array
    shared_jokes: str = "[]"           # JSON array
    notes: str = ""                    # 南瓜"记住"的关于此人的事
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


@dataclass
class Message:
    message_id: Optional[int] = None
    user_id: str = ""
    direction: Direction = Direction.INCOMING
    content: str = ""
    persona_state: str = "{}"          # JSON: mood, energy_level, time_of_day
    deep_topic: bool = False           # LLM 标注的深度话题标记
    has_open_loop: bool = False        # 消息含未来事件信号
    created_at: Optional[str] = None


@dataclass
class RelationshipEvent:
    event_id: Optional[int] = None
    user_id: str = ""
    event_type: str = ""               # first_contact, escalation, deescalation, correction, milestone
    old_state: str = "{}"
    new_state: str = "{}"
    trigger_message_id: Optional[int] = None
    created_at: Optional[str] = None


@dataclass
class Correction:
    correction_id: Optional[int] = None
    user_id: Optional[str] = None
    source: str = ""                   # user_said, self_reflection, evolution
    target_file: str = ""              # persona.md, self.md, skill.md
    description: str = ""
    applied: bool = False
    created_at: Optional[str] = None


@dataclass
class ProactiveTask:
    task_id: Optional[int] = None
    user_id: str = ""
    trigger_type: TriggerType = TriggerType.INACTIVITY
    proposed_message: str = ""
    status: str = "pending"            # pending, approved, sent, cancelled
    scheduled_for: Optional[str] = None
    sent_at: Optional[str] = None
    created_at: Optional[str] = None


@dataclass
class LifeEvent:
    event_id: Optional[int] = None
    event_type: str = ""               # academic, sports, social, reflection, known_character
    category: str = ""                 # daily, deep, night_reflection
    description: str = ""              # 自然语言描述
    characters_involved: str = "[]"    # JSON array of character names
    emotion: str = ""                  # 当时的情绪
    causality_chain_id: Optional[str] = None  # 因果链 ID
    shared_with_users: str = "[]"      # 已经跟哪些用户分享过
    created_at: Optional[str] = None


@dataclass
class EvolutionEntry:
    entry_id: Optional[int] = None
    cycle_date: str = ""               # 反思周期日期
    behavior_patterns_checked: str = "[]"  # 对照 Layer 5 哪些模式做了自检
    findings: str = ""                 # 自诊发现
    growth_notes: str = ""             # 成长记录
    written_back: bool = False         # 是否已写回 self.md
    shared_with_user: bool = False     # 是否已分享给用户
    created_at: Optional[str] = None


class ArcStatus(str, Enum):
    SETUP = "setup"
    RISING = "rising"
    CLIMAX = "climax"
    AFTERMATH = "aftermath"
    DORMANT = "dormant"  # 已结束/烂尾


@dataclass
class SocialCharacter:
    character_id: str = ""
    name: str = ""
    source: str = "fictional"           # self_md | fictional
    traits: str = "[]"                  # JSON array
    core_tension: str = ""              # 核心矛盾
    relationship_to_nan_gua: str = ""
    current_arc_id: Optional[str] = None
    arc_cooldown_until: Optional[str] = None
    status: str = "active"
    allowed_arc_types: str = "[]"       # JSON array


@dataclass
class SocialArc:
    arc_id: str = ""
    character_id: str = ""
    arc_type: str = ""                  # romance | conflict | growth | daily
    status: ArcStatus = ArcStatus.SETUP
    trigger_source: str = ""            # time | relation | random | conversation
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    event_count: int = 0
    max_events: int = 4                 # 此弧预计生成的事件数


@dataclass
class PersonaState:
    """当前人格快照 — 影响 LLM 生成行为。"""
    mood: str = "neutral"              # happy, neutral, sad, anxious, reflective
    energy_level: float = 0.5          # 0.0-1.0
    night_mode: bool = False           # 22:00-02:00
    recent_events_count: int = 0       # 最近生成的社交事件数
    last_reflection_date: Optional[str] = None


@dataclass
class Summary:
    """温记忆摘要。"""
    summary_id: Optional[int] = None
    user_id: str = ""
    summary_text: str = ""
    message_range_start: int = 0
    message_range_end: int = 0
    created_at: Optional[str] = None


@dataclass
class OpenLoop:
    """情节记忆——未完待续的事。"""
    loop_id: Optional[int] = None
    user_id: str = ""
    description: str = ""
    detected_at: Optional[str] = None
    follow_up_window: str = ""
    status: str = "open"
    closed_at: Optional[str] = None
    created_at: Optional[str] = None


@dataclass
class EmotionalPeak:
    """情感加权标记。"""
    peak_id: Optional[int] = None
    user_id: str = ""
    message_id: int = 0
    weight: int = 1
    signals: str = "[]"
    created_at: Optional[str] = None
