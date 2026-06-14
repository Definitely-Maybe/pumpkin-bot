"""tests/test_cold_index.py"""
from src.memory.cold_index import ColdIndex, extract_keywords


def test_extract_keywords_basic():
    kw = extract_keywords("我最近养了一只猫")
    assert "最近" in kw or "一只" in kw or "猫" in kw
    assert "的" not in kw  # stop word


def test_extract_keywords_filters_stop_words():
    kw = extract_keywords("我觉得可能是这样")
    assert "觉得" not in kw
    assert "可能" not in kw


def test_build_empty_notes():
    ci = ColdIndex()
    ci.build(None)
    assert ci.size == 0


def test_build_parses_notes():
    notes = "- 用户怕猫\n- 用户在准备考研\n- 用户喜欢打篮球"
    ci = ColdIndex()
    ci.build(notes)
    assert ci.size == 3


def test_search_triggers_relevant_note():
    notes = "- 用户怕猫\n- 用户在准备考研\n- 用户喜欢打篮球"
    ci = ColdIndex()
    ci.build(notes)
    results = ci.search("我昨天看到一只猫好可爱", max_results=3)
    assert any("怕猫" in r for r in results)


def test_search_no_match_returns_empty():
    notes = "- 用户怕猫\n- 用户喜欢打篮球"
    ci = ColdIndex()
    ci.build(notes)
    results = ci.search("今天天气真好", max_results=3)
    assert results == []


def test_build_replaces_old_index():
    ci = ColdIndex()
    ci.build("- first note")
    ci.build("- second note")
    assert ci.size == 1
