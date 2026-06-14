"""tests/test_evolution_writeback.py"""
import os
import tempfile
import json
from pathlib import Path
from src.evolution.writeback import WriteBack


SAMPLE_SELF_MD = """# 半个南瓜 — Self Memory v3.0

## 核心身份
- 名字：半个南瓜

## 三段感情
老内容
"""

SAMPLE_PERSONA_MD = """# 半个南瓜 — Persona v3.0

## Layer 0：硬规则

1. 你是半个南瓜
2. 不说"好哦"

## Layer 1：身份锚定

- 名字：半个南瓜
- INFP

## Layer 2：说话风格

- 用hhhhh
"""


class TestSelfMdAppend:
    def test_append_insights(self):
        with tempfile.TemporaryDirectory() as tmp:
            self_path = Path(tmp) / "self.md"
            self_path.write_text(SAMPLE_SELF_MD, encoding="utf-8")
            versions_dir = Path(tmp) / "versions"
            versions_dir.mkdir()

            result = {
                "self_insights": [{
                    "trigger": "wtt发了消息",
                    "old_view": "觉得放下了",
                    "new_view": "其实没放下",
                    "confidence": 0.8,
                }],
                "persona_changes": [],
                "growth_note": "这周发现自己在wtt问题上还是自欺欺人",
            }

            WriteBack.append_self_md(str(self_path), result, str(versions_dir))
            content = self_path.read_text(encoding="utf-8")
            assert "🧠 进化记录" in content
            assert "wtt发了消息" in content
            assert "其实没放下" in content
            assert "这周发现自己在wtt问题上还是自欺欺人" in content
            # 原始内容仍在
            assert "三段感情" in content

    def test_no_insights_skips_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            self_path = Path(tmp) / "self.md"
            self_path.write_text(SAMPLE_SELF_MD, encoding="utf-8")
            versions_dir = Path(tmp) / "versions"

            result = {
                "self_insights": [],
                "persona_changes": [],
                "growth_note": "",
            }
            WriteBack.append_self_md(str(self_path), result, str(versions_dir))
            # 无变化
            assert self_path.read_text(encoding="utf-8") == SAMPLE_SELF_MD


class TestSnapshot:
    def test_snapshot_creates_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            self_path = Path(tmp) / "self.md"
            self_path.write_text(SAMPLE_SELF_MD, encoding="utf-8")
            versions_dir = Path(tmp) / "versions"

            WriteBack.snapshot(str(self_path), str(versions_dir), tag="2026-06-21")
            snaps = list(versions_dir.glob("self_*.md"))
            assert len(snaps) == 1
            assert snaps[0].read_text(encoding="utf-8") == SAMPLE_SELF_MD


class TestChangelog:
    def test_changelog_append(self):
        with tempfile.TemporaryDirectory() as tmp:
            versions_dir = Path(tmp) / "versions"
            versions_dir.mkdir()

            result = {
                "self_insights": [{
                    "trigger": "x",
                    "old_view": "a",
                    "new_view": "b",
                    "confidence": 0.9,
                }],
                "persona_changes": [{
                    "target_layer": "1",
                    "rule_type": "add",
                    "old_text": "",
                    "new_text": "新规则",
                    "reason": "测试",
                }],
                "growth_note": "本周成长",
            }
            WriteBack.append_changelog(str(versions_dir), result, trigger_reason="定时反思")
            changelog = (versions_dir / "CHANGELOG.md").read_text(encoding="utf-8")
            assert "定时反思" in changelog
            assert "新规则" in changelog
            assert "本周成长" in changelog


class TestPersonaUpdate:
    def test_add_rule(self):
        with tempfile.TemporaryDirectory() as tmp:
            pers_path = Path(tmp) / "persona.md"
            pers_path.write_text(SAMPLE_PERSONA_MD, encoding="utf-8")

            WriteBack.apply_persona_delta(str(pers_path), [{
                "target_layer": "1",
                "rule_type": "add",
                "old_text": "",
                "new_text": "- 新增规则：测试",
                "reason": "test",
            }], str(Path(tmp) / "versions"))
            content = pers_path.read_text(encoding="utf-8")
            assert "新增规则：测试" in content

    def test_modify_rule(self):
        with tempfile.TemporaryDirectory() as tmp:
            pers_path = Path(tmp) / "persona.md"
            pers_path.write_text(SAMPLE_PERSONA_MD, encoding="utf-8")

            WriteBack.apply_persona_delta(str(pers_path), [{
                "target_layer": "0",
                "rule_type": "modify",
                "old_text": '2. 不说"好哦"',
                "new_text": '2. 偶尔可以说"好哦"',
                "reason": "test",
            }], str(Path(tmp) / "versions"))
            content = pers_path.read_text(encoding="utf-8")
            assert '偶尔可以说"好哦"' in content
            assert '不说"好哦"' not in content

    def test_delete_rule_strikethrough(self):
        with tempfile.TemporaryDirectory() as tmp:
            pers_path = Path(tmp) / "persona.md"
            pers_path.write_text(SAMPLE_PERSONA_MD, encoding="utf-8")

            WriteBack.apply_persona_delta(str(pers_path), [{
                "target_layer": "2",
                "rule_type": "delete",
                "old_text": "- 用hhhhh",
                "new_text": "",
                "reason": "test",
            }], str(Path(tmp) / "versions"))
            content = pers_path.read_text(encoding="utf-8")
            assert "~~- 用hhhhh~~" in content

    def test_version_bump(self):
        with tempfile.TemporaryDirectory() as tmp:
            pers_path = Path(tmp) / "persona.md"
            pers_path.write_text(SAMPLE_PERSONA_MD, encoding="utf-8")
            old_version = WriteBack._extract_version(SAMPLE_PERSONA_MD)
            assert old_version == "3.0"

            WriteBack._bump_version(str(pers_path))
            content = pers_path.read_text(encoding="utf-8")
            assert "v3.1" in content
