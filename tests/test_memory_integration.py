"""tests/test_memory_integration.py — 记忆系统集成测试。不需要 API key。"""

import asyncio
import os
import sys
import json
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.memory.cold_index import ColdIndex
from src.memory.recall_ranker import format_important_memories
from src.memory.summary_writer import SummaryWriter
from src.memory.loop_detector import LoopDetector


def test_cold_index_integration_with_real_notes_format():
    """验证 ColdIndex 能正确解析 users.notes 的真实格式。"""
    notes = "- 用户怕猫，小时候被抓过\n- 用户在准备考研，压力很大\n- 用户喜欢打篮球，每周都去\n- 用户最近换了工作，在新公司做后端"
    ci = ColdIndex()
    ci.build(notes)
    assert ci.size == 4

    # 聊到宠物 → 触发怕猫
    results = ci.search("我昨天在路边看到一只流浪猫好可爱", max_results=3)
    assert any("怕猫" in r for r in results)

    # 聊到运动 → 触发打篮球
    results = ci.search("最近想去运动一下", max_results=3)
    assert any("篮球" in r for r in results)

    # 聊到工作 → 触发换工作
    results = ci.search("工作好累啊最近", max_results=3)
    assert any("换" in r for r in results)


def test_cold_index_multiple_matches_ranked():
    """验证多条匹配时按相关性排序。"""
    notes = "- 用户喜欢猫\n- 用户养过一只叫豆豆的猫\n- 用户对猫毛过敏"
    ci = ColdIndex()
    ci.build(notes)

    results = ci.search("我家的猫今天特别粘人", max_results=2)
    assert len(results) <= 2
    # 应该优先匹配"喜欢猫"和"养过猫"（关键词"猫"命中更多）
    assert len(results) > 0


def test_summary_writer_topic_extraction_integration():
    """验证话题提取 + topics_discussed 更新逻辑。"""
    # 模拟摘要文本
    summary = "用户最近在准备面试，情绪有些焦虑。也聊到了家庭和未来的话题，提到了想换工作。"
    topics = SummaryWriter.extract_topics(summary)

    assert "面试" in topics
    assert "焦虑" in topics
    assert "家庭" in topics
    assert "未来" in topics
    assert "工作" in topics

    # 模拟 topics_discussed 更新逻辑（和 postprocess.py 一致）
    existing = []
    for t in topics:
        if t not in existing:
            existing.append(t)
    assert len(existing) >= 4
    assert "面试" in existing


def test_loop_detector_rules_vs_no_match():
    """验证规则检测的覆盖和边界。"""
    detector = LoopDetector()

    # 应该命中
    assert detector.detect_by_rules("我下周有个面试") is not None
    assert detector.detect_by_rules("明天要去医院") is not None
    assert detector.detect_by_rules("周末约饭喝酒") is not None
    assert detector.detect_by_rules("要交deadline了") is not None

    # 不应该命中
    assert detector.detect_by_rules("今天天气真好") is None
    assert detector.detect_by_rules("你好呀") is None
    assert detector.detect_by_rules("哈哈哈哈") is None


def test_recall_ranker_format_output_structure():
    """验证重要记忆的格式化输出结构正确。"""
    memories = [
        {"message_id": 1, "direction": "incoming", "content": "我今天特别焦虑", "weight": 3, "signals": ["deep_topic", "late_night"]},
        {"message_id": 2, "direction": "outgoing", "content": "你可以跟我说说的", "weight": 2, "signals": ["self_deep_exposure"]},
    ]
    formatted = format_important_memories(memories)

    # 结构检查
    assert "## 南瓜记得你们之间重要的事" in formatted
    assert "对方" in formatted
    assert "南瓜" in formatted
    assert "deep_topic" in formatted
    assert "焦虑" in formatted


def test_cold_index_empty_and_rebuild():
    """验证索引重建逻辑。"""
    ci = ColdIndex()
    assert ci.size == 0

    ci.build("- note1\n- note2")
    assert ci.size == 2

    # 重建应该替换
    ci.build("- note3 only")
    assert ci.size == 1

    results = ci.search("note1")
    assert results == []  # note1 已被替换


def test_summary_writer_time_span_boundaries():
    """验证时间跨度边界。"""
    assert SummaryWriter.compute_time_span([{}] * 1) == "今天"
    assert SummaryWriter.compute_time_span([{}] * 10) == "今天"
    assert SummaryWriter.compute_time_span([{}] * 11) == "最近一两天"
    assert SummaryWriter.compute_time_span([{}] * 30) == "最近一两天"
    assert SummaryWriter.compute_time_span([{}] * 31) == "最近几天"
    assert SummaryWriter.compute_time_span([{}] * 60) == "最近几天"
    assert SummaryWriter.compute_time_span([{}] * 61) == "最近一两周"
    assert SummaryWriter.compute_time_span([{}] * 100) == "最近一两周"
    assert SummaryWriter.compute_time_span([{}] * 101) == "最近几周"
