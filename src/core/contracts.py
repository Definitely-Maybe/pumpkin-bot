"""Pipeline 阶段间的 dataclass 契约。每个阶段输入/输出类型明确。"""

from dataclasses import dataclass, field
from typing import Optional

from ..storage.models import User, RelationshipType, PersonaState


@dataclass
class MessageContext:
    """Adapter -> Stage 1"""
    user_id: str
    raw_text: str
    timestamp: str
    platform: str = "terminal"


@dataclass
class UserSession:
    """Stage 1 -> Stage 2"""
    user: User
    relationship: RelationshipType
    persona_state: PersonaState
    history: list[dict] = field(default_factory=list)
    warm_summary: Optional[str] = None       # 温记忆最新摘要
    cold_notes: Optional[str] = None          # users.notes 冷记忆


@dataclass
class PromptContext:
    """Stage 2 -> Stage 3"""
    system_prompt: str
    messages: list[dict]          # OpenAI 格式 [{"role":..., "content":...}]
    sidecar_instruction: str      # 让 LLM 输出 sidecar JSON 的指令片段
    fallback_data: dict           # JSON 解析失败时的规则兜底数据


@dataclass
class LLMResponse:
    """Stage 3 -> Stage 4"""
    reply_text: str               # LLM 原始回复（已去除 JSON 块）
    deep_topic: bool
    mood: str                     # happy/neutral/sad/anxious/reflective
    worth_remembering: Optional[str] = None
    tokens: int = 0
    sidecar_parse_ok: bool = True  # JSON 解析是否成功


@dataclass
class OutgoingBurst:
    """Stage 4 -> Adapter"""
    messages: list[str]           # 拆分后的短句列表
    delay_ms: int = 800           # 发送间隔（毫秒）
