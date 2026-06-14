"""解析 persona.md 的 5 层结构。支持分层提取——L0-3 常驻、L4-5 按需注入。"""

from dataclasses import dataclass, field
import re

# ─── 保留原有 PersonaRules dataclass（兼容旧代码）───

@dataclass
class PersonaRules:
    hard_rules: list[str] = field(default_factory=list)
    identity: dict = field(default_factory=dict)
    speech: dict = field(default_factory=dict)
    emotion: dict = field(default_factory=dict)
    interpersonal: dict = field(default_factory=dict)
    behavior_patterns: dict = field(default_factory=dict)
    raw_text: str = ""


def parse_persona(md_content: str) -> PersonaRules:
    """保留原有接口——向后兼容。"""
    layers = extract_layers(md_content)
    return PersonaRules(raw_text=layers["L0_3"])


def extract_layers(md_content: str) -> dict[str, str]:
    """从 persona.md 提取分层内容。

    Returns:
        {
            "L0_3": str,   # Layer 0-3 原文（约 140 行），常驻 system prompt
            "L4": str,     # Layer 4 原文，按关系类型注入
            "L5": str,     # Layer 5 原文，按行为信号注入
        }
    """
    lines = md_content.split("\n")

    # 找每个 Layer 标题的行号
    layer_starts = {}
    for i, line in enumerate(lines):
        m = re.match(r"^## Layer (\d)", line.strip())
        if m:
            layer_starts[int(m.group(1))] = i

    # 取 Layer 0 到 Layer 3（包含 Layer 3 的全部内容直到 Layer 4）
    l0_start = layer_starts.get(0, 0)
    l4_start = layer_starts.get(4, len(lines))
    l5_start = layer_starts.get(5, len(lines))

    l0_3 = "\n".join(lines[l0_start:l4_start]).strip()
    l4 = "\n".join(lines[l4_start:l5_start]).strip()

    # Layer 5 到文件末尾（或下一个 ## 非 Layer 标题）
    end = len(lines)
    for i in range(l5_start + 1, len(lines)):
        if lines[i].strip().startswith("## ") and not lines[i].strip().startswith("## Layer"):
            end = i
            break
    l5 = "\n".join(lines[l5_start:end]).strip()

    return {"L0_3": l0_3, "L4": l4, "L5": l5}


def build_system_prompt(
    l0_3: str,
    extra_context: list[str] | None = None,
) -> str:
    """从 Layer 0-3 原文 + 额外上下文拼装 system prompt。

    extra_context: 时间上下文、关系上下文、Layer 4 规则、self.md 检索、记忆层 等
    """
    parts = [l0_3]
    if extra_context:
        parts.append("\n---\n")
        parts.append("\n\n".join(extra_context))
    return "\n".join(parts)
