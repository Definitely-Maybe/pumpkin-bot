"""self.md 话题检索——bot 独立运行时的等效实现。

Claude Code Skill 环境下，AI 用 Grep → Read 检索 self.md。
独立 bot 没有这些工具——这个模块用文件扫描实现同等功能。
"""

from pathlib import Path
from typing import Optional

# 话题触发词 → self.md 章节标题映射
TOPIC_TRIGGERS: dict[str, str] = {
    "毛桃": "### wtt（吴田田",
    "wtt": "### wtt（吴田田",
    "吴田田": "### wtt（吴田田",
    "ccx": "### 蔡楚娴（ccx",
    "蔡楚娴": "### 蔡楚娴（ccx",
    "豆豆": "### mxt（毛雪婷",
    "mxt": "### mxt（毛雪婷",
    "毛雪婷": "### mxt（毛雪婷",
    "马哥": "### MCYY",
    "MCYY": "### MCYY",
    "小马": "### MCYY",
    "马朝源": "### MCYY",
    "颜姐": "### 颜佳琳",
    "颜佳琳": "### 颜佳琳",
    "台晓丹": "### 台晓丹",
    "台老师": "### 台晓丹",
    "杭州": "### 家庭背景",
    "上海": "### 城市情感映射",
    "合肥": "### 城市情感映射",
    "弟弟": "### 家庭背景",
    "爸妈": "### 家庭背景",
    "家人": "### 家庭背景",
    "用力过猛": "## 行为模式",
    "考试模型": "## 行为模式",
    "小孩儿": "### 「小孩儿」身份叙事",
    "防火墙": "### 「防火墙理论」",
    "树洞": "## 行为模式",
    "雄竞": "### 「雄竞」框架",
    "被权衡": "## 行为模式",
    "迭代需求": "### 蔡楚娴（ccx）",
    "完结撒花": "### wtt（吴田田）",
    "queue": "### wtt（吴田田）",
}


class SelfMemory:
    """self.md 检索器——bot 独立运行时使用。"""

    def __init__(self, self_md_path: str | Path):
        self.path = Path(self_md_path)
        self._content: Optional[str] = None
        self._line_index: Optional[dict[str, int]] = None

    @property
    def content(self) -> str:
        if self._content is None:
            self._load()
        return self._content

    def _load(self) -> None:
        """加载 self.md 并建立标题→行号索引。"""
        self._content = self.path.read_text(encoding="utf-8")
        self._line_index = {}
        for i, line in enumerate(self._content.split("\n")):
            stripped = line.strip()
            if stripped.startswith("## ") or stripped.startswith("### "):
                self._line_index[stripped] = i

    def reload(self) -> None:
        """重新加载（用于 hot-reload）。"""
        self._content = None
        self._line_index = None
        self._load()

    def search(self, user_message: str, context_lines: int = 80) -> str:
        """根据用户消息中的触发词检索相关章节。

        返回最相关的章节内容，或空字符串。
        """
        matched: list[str] = []
        for keyword, heading in TOPIC_TRIGGERS.items():
            if keyword.lower() in user_message.lower():
                section = self.get_section(heading, context_lines)
                if section:
                    matched.append(section)
                if len(matched) >= 2:  # 最多返回两个章节
                    break

        if not matched:
            return ""

        return (
            "【关于这个主题，南瓜知道以下事。用模糊感觉而非精确数据——"
            "不要说日期、标签、原文。】\n" + "\n---\n".join(matched)
        )

    def get_section(self, heading: str, max_lines: int = 100) -> str:
        """获取指定标题的章节内容。用 startswith 匹配（兼容标题变体）。"""
        if self._line_index is None:
            self._load()

        # 先精确匹配，再 startswith 模糊匹配
        if heading in self._line_index:
            start = self._line_index[heading]
        else:
            start = None
            for h, line_no in self._line_index.items():
                if h.startswith(heading):
                    start = line_no
                    break

        if start is None:
            return ""

        lines = self.content.split("\n")
        end = min(start + max_lines, len(lines))

        return "\n".join(lines[start:end])
