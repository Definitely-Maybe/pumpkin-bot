"""tests/test_evolution_integration.py — 人格进化集成测试。不需要 API key。"""
import json
import tempfile
from pathlib import Path
from src.evolution.reflector import Reflector
from src.evolution.writeback import WriteBack
from src.evolution.engine import EvolutionEngine


SAMPLE_SELF_MD = """# 半个南瓜 — Self Memory v3.0
## 核心身份
- 半个南瓜
## 三段感情
### wtt（吴田田）
以前觉得放下了
"""

SAMPLE_PERSONA_MD = """# 半个南瓜 — Persona v3.0
## Layer 0：硬规则
1. 你是半个南瓜
2. 不说"好哦"
## Layer 1：身份锚定
- 名字：半个南瓜
## Layer 2：说话风格
- 用hhhhh
"""


class TestFullReflectionCycle:
    """模拟完整的反思→写回周期。"""

    def test_assemble_parse_write_roundtrip(self):
        """组装输入 → 解析输出 → 写回文件 → 验证文件内容。"""
        with tempfile.TemporaryDirectory() as tmp:
            self_path = Path(tmp) / "self.md"
            pers_path = Path(tmp) / "persona.md"
            versions_dir = Path(tmp) / "versions"
            versions_dir.mkdir()
            self_path.write_text(SAMPLE_SELF_MD, encoding="utf-8")
            pers_path.write_text(SAMPLE_PERSONA_MD, encoding="utf-8")

            # 1. 组装输入
            input_text = Reflector.assemble_input(
                summaries=[{"summary_text": "聊了情感话题"}],
                recent_corrections=[{"description": "不说好哦"}],
                recent_social_events=[{"description": "wtt给南瓜发了消息"}],
                emotional_peaks=[{"signals": '["深夜emo"]', "weight": 3}],
                deep_ratio_change=0.1,
                late_night_ratio_change=0.05,
                self_md_sections="### wtt（吴田田）\n以前觉得放下了",
                persona_baseline="Layer 0\n1. 你是半个南瓜",
            )
            assert "wtt" in input_text
            assert "情感话题" in input_text

            # 2. 模拟 LLM 输出
            raw = json.dumps({
                "self_insights": [{
                    "trigger": "wtt发了消息",
                    "old_view": "觉得放下了",
                    "new_view": "其实还是在意",
                    "confidence": 0.85,
                }],
                "persona_changes": [{
                    "target_layer": "0",
                    "rule_type": "modify",
                    "old_text": '2. 不说"好哦"',
                    "new_text": '2. 偶尔可以说"好哦"',
                    "reason": "用户反馈",
                }],
                "growth_note": "发现自己在wtt的问题上还是自欺欺人",
            })

            result = Reflector.parse_response(raw)
            assert result is not None
            assert len(result["self_insights"]) == 1
            assert len(result["persona_changes"]) == 1

            # 3. 写回
            # Snapshot
            s1 = WriteBack.snapshot(str(self_path), str(versions_dir), "2026-06-21")
            s2 = WriteBack.snapshot(str(pers_path), str(versions_dir), "v3.0")
            assert s1 and Path(s1).exists()
            assert s2 and Path(s2).exists()

            # Changelog
            WriteBack.append_changelog(str(versions_dir), result, "定时反思")
            cl = (versions_dir / "CHANGELOG.md").read_text(encoding="utf-8")
            assert "定时反思" in cl

            # self.md 追加
            WriteBack.append_self_md(str(self_path), result, str(versions_dir))
            self_content = self_path.read_text(encoding="utf-8")
            assert "🧠 进化记录" in self_content
            assert "其实还是在意" in self_content

            # persona.md 更新
            WriteBack.apply_persona_delta(
                str(pers_path), result["persona_changes"], str(versions_dir),
            )
            pers_content = pers_path.read_text(encoding="utf-8")
            assert "偶尔可以说" in pers_content
            assert "v3.1" in pers_content


class TestTriggerHelpers:
    def test_all_decision_methods_work_together(self):
        """验证触发决策链：定时 → 活动检查 → 间隔检查 → 上限检查。"""
        # 无最后记录 → 不卡间隔
        assert EvolutionEngine._within_min_interval(None, 48) is False
        # 周日 23:00 匹配
        assert EvolutionEngine._check_scheduled(6, 23, 6, 23) is True
        # 本周 0 次 → 不限
        assert EvolutionEngine._weekly_cap_reached(0, 2) is False
        # 本周 2 次 → 上限
        assert EvolutionEngine._weekly_cap_reached(2, 2) is True
