"""tests/test_rules.py — 验证 persona.md 分层提取。"""

from src.persona.rules import extract_layers


def test_extract_layers_returns_all_five():
    md = """## Layer 0：硬规则
rules here
## Layer 1：身份锚定
identity here
## Layer 2：说话风格
speech here
## Layer 3：情感与决策模式
emotion here
## Layer 4：人际行为
interpersonal here
## Layer 5：行为模式与防火墙
patterns here"""

    layers = extract_layers(md)
    assert "## Layer 0" in layers["L0_3"]
    assert "## Layer 3" in layers["L0_3"]
    assert "## Layer 4" not in layers["L0_3"]
    assert "## Layer 4" in layers["L4"]
    assert "## Layer 5" in layers["L5"]


def test_layers_dont_overlap():
    md = """## Layer 0：硬规则
hello
## Layer 1：身份锚定
world
## Layer 2：说话风格
foo
## Layer 3：情感与决策模式
bar
## Layer 4：人际行为
baz
## Layer 5：行为模式与防火墙
qux"""

    layers = extract_layers(md)
    assert "## Layer 4" not in layers["L0_3"]
    assert "## Layer 5" not in layers["L0_3"]
    assert "## Layer 4" not in layers["L5"]
    assert "## Layer 5" not in layers["L4"]
