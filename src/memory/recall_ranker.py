"""记忆召回排序 — 情感峰值驱动优先级。"""

import json
from typing import Optional
import aiosqlite


async def get_important_memories(
    conn: aiosqlite.Connection,
    user_id: str,
    limit: int = 5,
) -> list[dict]:
    """获取用户最重要的消息（按情感权重排序）。

    Returns: [{message_id, direction, content, weight, signals}, ...]
    """
    cursor = await conn.execute(
        """SELECT p.weight, p.signals, m.direction, m.content, m.message_id
           FROM emotional_peaks p
           JOIN messages m ON p.message_id = m.message_id
           WHERE p.user_id = ?
           ORDER BY p.weight DESC, p.created_at DESC
           LIMIT ?""",
        (user_id, limit),
    )
    rows = await cursor.fetchall()
    return [
        {
            "message_id": r["message_id"],
            "direction": r["direction"],
            "content": r["content"][:300],  # 截断
            "weight": r["weight"],
            "signals": json.loads(r["signals"]) if r["signals"] else [],
        }
        for r in rows
    ]


def format_important_memories(memories: list[dict]) -> str:
    """将重要记忆格式化为 system prompt 注入段落。

    Returns: 格式化的记忆文本，或空字符串。
    """
    if not memories:
        return ""

    lines = ["## 南瓜记得你们之间重要的事"]
    for mem in memories:
        role = "对方" if mem["direction"] == "incoming" else "南瓜"
        signals_str = ", ".join(mem["signals"])
        lines.append(f"- [{role}] {mem['content'][:150]}（{signals_str}）")

    return "\n".join(lines)
