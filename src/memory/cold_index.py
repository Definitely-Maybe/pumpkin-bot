"""冷记忆关联索引 — 聊到猫 → 想起用户怕猫。"""

import re
from typing import Optional


# 中文分词简化：关键词提取（去掉常见停用词）
_STOP_WORDS = {
    "的", "了", "是", "我", "你", "他", "她", "它", "们", "在", "有", "不",
    "这", "那", "就", "也", "都", "要", "会", "和", "很", "个", "说", "想",
    "觉得", "可能", "应该", "因为", "所以", "但是", "虽然", "如果", "大概",
    "好像", "可能", "有一点", "非常", "比较",
}


def extract_keywords(text: str) -> set[str]:
    """从文本提取关键词（2-4 字的实词片段）。"""
    # 移除标点
    cleaned = re.sub(r"[^一-鿿]", " ", text)
    words = set()
    for w in cleaned.split():
        # Single non-stop characters (meaningful: 猫 → cat)
        for ch in w:
            if ch not in _STOP_WORDS:
                words.add(ch)
        # Multi-character words (2+)
        if len(w) >= 2 and w not in _STOP_WORDS:
            words.add(w)
        # 再加 2-3 字滑动窗口片段（过滤停用词）
        if len(w) >= 3:
            for i in range(len(w) - 2):
                frag = w[i:i+2]
                if frag not in _STOP_WORDS:
                    words.add(frag)
    return words


class ColdIndex:
    """冷记忆倒排索引。"""

    def __init__(self):
        # keyword → [note_index, ...]
        self._index: dict[str, list[int]] = {}
        self._notes: list[str] = []  # 原始笔记条目

    def build(self, notes_text: str | None):
        """从 users.notes 字段构建索引。"""
        self._index.clear()
        self._notes.clear()

        if not notes_text:
            return

        # notes 格式：每行 "- 内容"
        for line in notes_text.split("\n"):
            stripped = line.strip()
            if stripped.startswith("- "):
                entry = stripped[2:].strip()
            else:
                entry = stripped
            if not entry:
                continue

            idx = len(self._notes)
            self._notes.append(entry)
            keywords = extract_keywords(entry)
            for kw in keywords:
                if kw not in self._index:
                    self._index[kw] = []
                self._index[kw].append(idx)

    def search(self, user_message: str, max_results: int = 3) -> list[str]:
        """根据用户消息触发关联的冷记忆条目。

        Returns: 匹配的 notes 条目列表（最多 max_results 条）
        """
        msg_keywords = extract_keywords(user_message)

        # 统计每个 note 的命中次数
        hits: dict[int, int] = {}
        for kw in msg_keywords:
            for note_idx in self._index.get(kw, []):
                hits[note_idx] = hits.get(note_idx, 0) + 1

        # 按命中数降序，取前 N
        ranked = sorted(hits.items(), key=lambda x: -x[1])
        return [self._notes[idx] for idx, _ in ranked[:max_results]]

    @property
    def size(self) -> int:
        """索引中条目数。"""
        return len(self._notes)
