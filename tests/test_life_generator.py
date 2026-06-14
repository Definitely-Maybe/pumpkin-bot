from datetime import datetime
import random

from src.simulation.life_generator import LifeGenerator


def test_generate_returns_life_event_dataclass():
    generator = LifeGenerator(rng=random.Random(1))

    event = generator.generate(now=datetime(2026, 6, 15, 14, 0, 0))

    assert event.event_type == "life"
    assert event.category in {"daily", "creative", "body_state", "reflection"}
    assert event.description
    assert event.emotion
    assert event.characters_involved == "[]"


def test_daily_is_default_weighted_kind():
    generator = LifeGenerator(rng=random.Random(3))
    counts = {"daily": 0, "creative": 0, "body_state": 0, "reflection": 0}

    for _ in range(100):
        event = generator.generate(now=datetime(2026, 6, 15, 14, 0, 0))
        counts[event.category] += 1

    assert counts["daily"] > counts["creative"]
    assert counts["daily"] > counts["reflection"]


def test_night_biases_toward_body_or_reflection():
    generator = LifeGenerator(rng=random.Random(2))

    categories = [
        generator.generate(now=datetime(2026, 6, 15, 23, 0, 0)).category
        for _ in range(30)
    ]

    assert "body_state" in categories or "reflection" in categories


def test_catchup_description_does_not_claim_exact_time():
    generator = LifeGenerator(rng=random.Random(4))

    event = generator.generate(
        now=datetime(2026, 6, 15, 12, 0, 0),
        reason="catchup",
    )

    assert "补档" not in event.description
    assert "系统" not in event.description
