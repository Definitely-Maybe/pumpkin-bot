"""WriteBack — 文件写回 + snapshot + CHANGELOG。"""

import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional


class WriteBack:
    """将 Reflector 的结构化输出写回文件系统。"""

    @staticmethod
    def snapshot(file_path: str, versions_dir: str, tag: str) -> Optional[str]:
        """保存文件快照。tag 是日期或版本号。"""
        src = Path(file_path)
        if not src.exists():
            return None
        dst_dir = Path(versions_dir)
        dst_dir.mkdir(parents=True, exist_ok=True)
        ext = src.suffix
        stem = src.stem
        dst = dst_dir / f"{stem}_{tag}{ext}"
        shutil.copy2(str(src), str(dst))
        return str(dst)

    @staticmethod
    def append_changelog(
        versions_dir: str, result: dict, trigger_reason: str,
    ) -> None:
        """追加一条进化记录到 CHANGELOG.md。"""
        dst_dir = Path(versions_dir)
        dst_dir.mkdir(parents=True, exist_ok=True)
        cl_path = dst_dir / "CHANGELOG.md"

        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        lines = [f"\n## {now} — {trigger_reason}\n"]

        insights = result.get("self_insights", [])
        if insights:
            lines.append("\n### 自我认知更新\n")
            for item in insights:
                lines.append(f"- **触发**：{item['trigger']}\n")
                if item.get("old_view"):
                    lines.append(f"  - 以前：{item['old_view']}\n")
                lines.append(f"  - 现在：{item['new_view']}\n")
                lines.append(f"  - 确信度：{item.get('confidence', 0.5)}\n")

        changes = result.get("persona_changes", [])
        if changes:
            lines.append("\n### 行为规则变更\n")
            for item in changes:
                rt = item["rule_type"]
                tl = item["target_layer"]
                lines.append(f"- **{rt}** @ Layer {tl}\n")
                if rt != "add" and item.get("old_text"):
                    lines.append(f"  - 旧：{item['old_text']}\n")
                if rt != "delete" and item.get("new_text"):
                    lines.append(f"  - 新：{item['new_text']}\n")
                if item.get("reason"):
                    lines.append(f"  - 原因：{item['reason']}\n")

        if result.get("growth_note"):
            lines.append(f"\n### 本周成长\n{result['growth_note']}\n")

        with open(cl_path, "a", encoding="utf-8") as f:
            f.writelines(lines)

    @staticmethod
    def append_self_md(
        self_md_path: str, result: dict, versions_dir: str,
    ) -> bool:
        """尾部追加进化记录到 self.md。返回是否实际写入。"""
        insights = result.get("self_insights", [])
        growth_note = result.get("growth_note", "")
        if not insights and not growth_note:
            return False

        today = datetime.now().strftime("%Y-%m-%d")
        lines = [f"\n## 🧠 进化记录 — {today}\n"]

        if insights:
            lines.append("\n### 洞察\n")
            for item in insights:
                lines.append(f"\n- **触发**：{item['trigger']}\n")
                if item.get("old_view"):
                    lines.append(f"  - 以前：{item['old_view']}\n")
                lines.append(f"  - 现在：{item['new_view']}\n")
                lines.append(f"  - 确信度：{item.get('confidence', 0.5)}\n")

        if growth_note:
            lines.append(f"\n### 本周成长\n\n{growth_note}\n")

        content = "".join(lines)

        with open(self_md_path, "a", encoding="utf-8") as f:
            f.write(content)

        return True

    @staticmethod
    def apply_persona_delta(
        persona_path: str, changes: list[dict], versions_dir: str,
    ) -> int:
        """原位更新 persona.md。返回成功应用的变更数。"""
        path = Path(persona_path)
        if not path.exists():
            return 0

        content = path.read_text(encoding="utf-8")
        original = content

        applied = 0
        for change in changes:
            rt = change["rule_type"]
            old_text = change.get("old_text", "")
            new_text = change.get("new_text", "")
            target_layer = change.get("target_layer", "")

            if rt == "add":
                # 在目标 Layer 末尾追加
                layer_marker = f"## Layer {target_layer}"
                marker_pos = content.find(layer_marker)
                if marker_pos == -1:
                    continue
                # 找到下一个 ## 的位置，在之前插入
                next_section = content.find("\n## ", marker_pos + len(layer_marker))
                if next_section == -1:
                    next_section = len(content)
                insert_pos = content.rfind("\n", 0, next_section)
                if insert_pos == -1:
                    insert_pos = next_section
                content = content[:insert_pos] + f"\n{new_text}" + content[insert_pos:]
                applied += 1

            elif rt == "modify":
                if old_text in content:
                    content = content.replace(old_text, new_text, 1)
                    applied += 1

            elif rt == "delete":
                if old_text in content:
                    content = content.replace(old_text, f"~~{old_text}~~", 1)
                    applied += 1

        if applied > 0 and content != original:
            WriteBack._bump_version_from_content(path, content)
            # _bump_version_from_content already writes the file

        return applied

    @staticmethod
    def _extract_version(text: str) -> Optional[str]:
        """从 persona.md 内容中提取版本号。"""
        m = re.search(r'# .+[Pp]ersona\s+v?(\d+\.\d+)', text)
        return m.group(1) if m else None

    @staticmethod
    def _bump_version(file_path: str) -> None:
        """原地 bump persona.md 的 patch 版本号。"""
        path = Path(file_path)
        content = path.read_text(encoding="utf-8")
        old_version = WriteBack._extract_version(content)
        if not old_version:
            return
        parts = old_version.split(".")
        parts[-1] = str(int(parts[-1]) + 1)
        new_version = ".".join(parts)
        content = content.replace(f"Persona v{old_version}", f"Persona v{new_version}", 1)
        content = content.replace(f"persona v{old_version}", f"persona v{new_version}", 1)
        path.write_text(content, encoding="utf-8")

    @staticmethod
    def _bump_version_from_content(file_path: Path, content: str) -> None:
        """基于已修改的内容 bump 版本号并写入。"""
        old_version = WriteBack._extract_version(content)
        if not old_version:
            file_path.write_text(content, encoding="utf-8")
            return
        parts = old_version.split(".")
        parts[-1] = str(int(parts[-1]) + 1)
        new_version = ".".join(parts)
        content = content.replace(f"Persona v{old_version}", f"Persona v{new_version}", 1)
        content = content.replace(f"persona v{old_version}", f"persona v{new_version}", 1)
        file_path.write_text(content, encoding="utf-8")
