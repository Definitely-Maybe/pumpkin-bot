"""对话纠正机制——检测用户纠正信号，写回 skill.md 的 Correction 记录。"""

import re
from datetime import datetime
from pathlib import Path
from typing import Optional

import aiosqlite

from ..storage import queries as q

# 纠正信号模式
CORRECTION_PATTERNS = [
    r"我不会这样说",
    r"我其实不会这样说",
    r"这不是我说的",
    r"这不对",
    r"我不这么说",
    r"我说话不是这样的",
    r"我不这样",
    r"我遇到这种情况[^的]",
    r"我应该是",
]


class CorrectionHandler:
    """检测用户纠正意图，生成纠正记录，写回 skill.md。"""

    def __init__(self, skill_md_path: str, db_conn: aiosqlite.Connection):
        self.skill_md_path = Path(skill_md_path)
        self.db = db_conn

    def detect(self, user_message: str) -> Optional[str]:
        """检测用户消息是否包含纠正信号。返回纠正描述，或 None。"""
        for pattern in CORRECTION_PATTERNS:
            if re.search(pattern, user_message):
                return f"用户说: {user_message.strip()}"
        return None

    async def handle(
        self,
        user_id: str,
        user_message: str,
        last_bot_reply: Optional[str] = None,
    ) -> bool:
        """处理纠正：检测 → 记录 → 写回。"""
        description = self.detect(user_message)
        if not description:
            return False

        # 补充上下文：bot 上一条说了什么
        if last_bot_reply:
            description += f"\nbot 上一条回复: {last_bot_reply[:200]}"

        # 记录到数据库
        await q.log_correction(
            self.db,
            user_id=user_id,
            source="user_said",
            target_file="skill.md",
            description=description,
            applied=False,
        )

        # 写回 skill.md 的 Correction 记录
        self._write_to_skill_md(description)

        return True

    def _write_to_skill_md(self, description: str) -> None:
        """将纠正追写到 skill.md 的 Correction 记录区域。"""
        if not self.skill_md_path.exists():
            return

        content = self.skill_md_path.read_text(encoding="utf-8")
        today = datetime.now().strftime("%Y-%m-%d")

        correction_entry = (
            f"\n- **{today} — 运行时纠正**：{description}"
        )

        # 找到 Correction 记录区域
        marker = "## Correction 记录"
        if marker in content:
            # 在 Correction 区域末尾插入（在下一个 ## 之前）
            idx = content.find(marker)
            # 找到下一个 ## 标题
            rest = content[idx + len(marker):]
            next_section = rest.find("\n## ")
            if next_section != -1:
                insert_pos = idx + len(marker) + next_section
                new_content = content[:insert_pos] + correction_entry + content[insert_pos:]
            else:
                new_content = content + correction_entry
        else:
            # 没有 Correction 区域，在文件末尾追加
            new_content = content + f"\n\n{marker}\n{correction_entry}\n"

        self.skill_md_path.write_text(new_content, encoding="utf-8")
