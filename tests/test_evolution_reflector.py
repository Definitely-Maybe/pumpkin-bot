"""tests/test_evolution_reflector.py"""
import json
import pytest
from src.evolution.reflector import Reflector


class TestAssembleInput:
    def test_empty_inputs_still_produces_prompt(self):
        """所有输入为空时也能组装出基本 prompt（含人格基线）。"""
        result = Reflector.assemble_input(
            summaries=[],
            recent_corrections=[],
            recent_social_events=[],
            emotional_peaks=[],
            deep_ratio_change=0.0,
            late_night_ratio_change=0.0,
            self_md_sections="",
            persona_baseline="Layer 0 + Layer 1 内容",
        )
        assert "Layer 0" in result
        assert "近期行为快照" in result

    def test_full_input_assembles_all_sections(self):
        """完整输入含所有 layer。"""
        result = Reflector.assemble_input(
            summaries=[{"summary_text": "用户聊了情感话题"}],
            recent_corrections=[{"description": "不说好哦"}],
            recent_social_events=[{"description": "wtt发了一条消息给南瓜"}],
            emotional_peaks=[{"signals": '["深夜emo"]', "weight": 3}],
            deep_ratio_change=0.05,
            late_night_ratio_change=-0.02,
            self_md_sections="### wtt（吴田田）\n...",
            persona_baseline="Layer 0\nLayer 1",
        )
        assert "近期行为快照" in result
        assert "情感信号" in result
        assert "关联回顾" in result
        assert "当前人格基线" in result
        assert "wtt" in result


class TestParseResponse:
    def test_valid_json_all_fields(self):
        raw = json.dumps({
            "self_insights": [{
                "trigger": "wtt发消息",
                "old_view": "放下了",
                "new_view": "其实没放下",
                "confidence": 0.8,
            }],
            "persona_changes": [],
            "growth_note": "本周发现...",
        })
        result = Reflector.parse_response(raw)
        assert result is not None
        assert len(result["self_insights"]) == 1
        assert result["self_insights"][0]["confidence"] == 0.8
        assert result["growth_note"] == "本周发现..."

    def test_valid_json_both_empty_returns_none(self):
        """两者都空 -> 跳过写回，返回 None。"""
        raw = json.dumps({
            "self_insights": [],
            "persona_changes": [],
            "growth_note": "没啥",
        })
        assert Reflector.parse_response(raw) is None

    def test_invalid_json_returns_none(self):
        assert Reflector.parse_response("这不是 JSON") is None

    def test_missing_confidence_defaults(self):
        raw = json.dumps({
            "self_insights": [{"trigger": "x", "old_view": "a", "new_view": "b"}],
            "persona_changes": [],
            "growth_note": "ok",
        })
        result = Reflector.parse_response(raw)
        assert result["self_insights"][0]["confidence"] == 0.5

    def test_persona_change_rule_type_must_be_valid(self):
        raw = json.dumps({
            "self_insights": [],
            "persona_changes": [{
                "target_layer": "1",
                "rule_type": "invalid_type",
                "old_text": "x",
                "new_text": "y",
                "reason": "test",
            }],
            "growth_note": "ok",
        })
        assert Reflector.parse_response(raw) is None

    def test_persona_change_modify_without_old_text(self):
        """modify 无 old_text -> 无效。"""
        raw = json.dumps({
            "self_insights": [],
            "persona_changes": [{
                "target_layer": "1",
                "rule_type": "modify",
                "new_text": "y",
                "reason": "test",
            }],
            "growth_note": "ok",
        })
        assert Reflector.parse_response(raw) is None

    def test_confidence_out_of_range(self):
        raw = json.dumps({
            "self_insights": [{
                "trigger": "x", "old_view": "a", "new_view": "b", "confidence": 1.5,
            }],
            "persona_changes": [],
            "growth_note": "ok",
        })
        # confidence > 1.0 -> 跳过该条 insight（不是整个结果无效）
        result = Reflector.parse_response(raw)
        assert result is not None
        assert len(result["self_insights"]) == 0
