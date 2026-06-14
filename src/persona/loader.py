"""persona.md / self.md / skill.md 文件加载器。"""

from pathlib import Path


def load_persona_md(path: str | Path) -> str:
    """读取 persona.md 完整内容。"""
    return _read_file(path)


def load_self_md(path: str | Path) -> str:
    """读取 self.md 完整内容。"""
    return _read_file(path)


def load_skill_md(path: str | Path) -> str:
    """读取 skill.md 完整内容。"""
    return _read_file(path)


def get_self_md_section(path: str | Path, heading: str, lines: int = 100) -> str:
    """按章节标题检索 self.md 的指定片段。

    通过 Grep 查找 heading 所在行号，Read 取 lines 行。
    这个方法在 Claude Code Skill 上下文中由 AI 调用；
    在 bot 独立运行时，由 memory.py 用文件扫描模拟。
    """
    content = _read_file(path)
    lines_list = content.split("\n")
    for i, line in enumerate(lines_list):
        if line.strip().startswith(heading):
            start = i
            end = min(i + lines, len(lines_list))
            return "\n".join(lines_list[start:end])
    return ""


def _read_file(path: str | Path) -> str:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Persona file not found: {path}")
    return path.read_text(encoding="utf-8")
