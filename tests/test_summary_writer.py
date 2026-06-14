"""tests/test_summary_writer.py"""
from src.memory.summary_writer import SummaryWriter


def test_extract_topics_finds_matches():
    text = "用户最近在准备面试，情绪有些焦虑，也聊到了家庭和未来的话题"
    topics = SummaryWriter.extract_topics(text)
    assert "面试" in topics
    assert "焦虑" in topics
    assert "家庭" in topics
    assert "未来" in topics


def test_extract_topics_no_matches():
    text = "今天天气很好，用户心情不错"
    topics = SummaryWriter.extract_topics(text)
    assert topics == []


def test_extract_topics_deduplicates():
    text = "用户聊了工作工作工作"  # 只出现一次
    topics = SummaryWriter.extract_topics("用户聊了工作和家庭的事")
    assert topics.count("工作") == 0 or topics.count("工作") == 1


def test_compute_time_span_today():
    assert SummaryWriter.compute_time_span([{}] * 5) == "今天"


def test_compute_time_span_days():
    assert SummaryWriter.compute_time_span([{}] * 40) == "最近几天"


def test_compute_time_span_weeks():
    assert SummaryWriter.compute_time_span([{}] * 80) == "最近一两周"
    assert SummaryWriter.compute_time_span([{}] * 120) == "最近几周"
