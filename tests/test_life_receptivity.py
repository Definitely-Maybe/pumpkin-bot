from src.simulation.life_receptivity import LifeReceptivity


def test_receptivity_defaults_to_neutral():
    result = LifeReceptivity.estimate([])

    assert result.score == 0.5
    assert result.label == "neutral"
    assert result.positive_hits == []
    assert result.negative_hits == []


def test_positive_receptivity_from_questions_and_care():
    messages = [
        {"role": "assistant", "content": "我今天有点低电量。"},
        {"role": "user", "content": "后来呢？你还好吗？别太累。"},
    ]

    result = LifeReceptivity.estimate(messages)

    assert result.score > 0.5
    assert result.label == "high"
    assert "follow_up" in result.positive_hits
    assert "care" in result.positive_hits


def test_negative_receptivity_from_refusal():
    messages = [
        {"role": "assistant", "content": "我今天出门的时候放空了。"},
        {"role": "user", "content": "不想听这个，先说我的事。"},
    ]

    result = LifeReceptivity.estimate(messages)

    assert result.score < 0.5
    assert result.label == "low"
    assert "explicit_refusal" in result.negative_hits


def test_recent_user_message_has_more_weight_than_old_message():
    messages = [
        {"role": "user", "content": "后来呢？"},
        {"role": "assistant", "content": "我昨天还挺累。"},
        {"role": "user", "content": "算了先不说这个。"},
    ]

    result = LifeReceptivity.estimate(messages)

    assert result.score < 0.5
    assert result.label == "low"
