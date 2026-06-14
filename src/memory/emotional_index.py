"""情感加权——不是所有消息权重相同。"""

from datetime import datetime

# 情感相关 emoji 集合
EMOTIONAL_EMOJI = {"😢", "😫", "😭", "🥲", "😤", "😡", "🥺", "💔", "😊", "🥰"}


def compute_weight(
    deep_topic: bool = False,
    hour: int | None = None,
    msg_len: int = 0,
    has_emoji: bool = False,
    is_self_deep_exposure: bool = False,
) -> int:
    """计算单条消息的情感权重（1-3）。

    各信号权重（取最高）：
    - deep_topic → 3x
    - 用户情绪表达 (emoji) → 3x
    - 深夜时段 (22:00-02:00) → 2x
    - 长段落 (>100字) → 2x
    - 南瓜深度暴露 → 2x
    - 默认 → 1x
    """
    weight = 1

    if deep_topic:
        weight = max(weight, 3)
    if has_emoji:
        weight = max(weight, 3)
    if hour is not None and (hour >= 22 or hour <= 2):
        weight = max(weight, 2)
    if msg_len > 100:
        weight = max(weight, 2)
    if is_self_deep_exposure:
        weight = max(weight, 2)

    return weight


def detect_emoji(text: str) -> bool:
    """检测文本中是否包含情感 emoji。"""
    return any(c in text for c in EMOTIONAL_EMOJI)


def extract_signals(
    deep_topic: bool = False,
    hour: int | None = None,
    msg_len: int = 0,
    has_emoji: bool = False,
    is_self_deep_exposure: bool = False,
) -> list[str]:
    """提取触发的信号列表（用于存入 emotional_peaks.signals JSON）。"""
    signals = []
    if deep_topic:
        signals.append("deep_topic")
    if has_emoji:
        signals.append("emoji")
    if hour is not None and (hour >= 22 or hour <= 2):
        signals.append("late_night")
    if msg_len > 100:
        signals.append("long_form")
    if is_self_deep_exposure:
        signals.append("self_deep_exposure")
    return signals if signals else ["default"]
