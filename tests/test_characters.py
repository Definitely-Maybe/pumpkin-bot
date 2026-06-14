"""tests/test_characters.py"""
import json
from src.social.characters import CharacterManager
from src.storage.models import SocialCharacter


def test_self_md_characters_exist():
    """验证 self.md 角色加载（至少 4 个）。"""
    chars = CharacterManager._load_self_md_characters()
    assert len(chars) >= 4
    names = [c.name for c in chars]
    assert "wtt" in names
    assert "ccx" in names


def test_self_md_characters_have_traits():
    chars = CharacterManager._load_self_md_characters()
    wtt = [c for c in chars if c.name == "wtt"][0]
    assert len(json.loads(wtt.traits)) >= 3
    assert "romance" in wtt.allowed_arc_types or "暧昧" in wtt.allowed_arc_types


def test_fictional_character_prompt_includes_core_tension():
    """验证虚构角色生成 prompt 要求 core_tension。"""
    prompt = CharacterManager._build_fictional_prompt(env_hint="华东师大")
    assert "core_tension" in prompt.lower() or "核心矛盾" in prompt
    assert "华东师大" in prompt


def test_require_romance_and_rival():
    """验证虚构角色约束：至少一个暧昧线、一个损友。"""
    prompt = CharacterManager._build_fictional_prompt(env_hint="")
    assert "暧昧" in prompt or "romance" in prompt.lower()
    assert "损友" in prompt or "互怼" in prompt
