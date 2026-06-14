from datetime import datetime, timedelta

from src.simulation.catchup_planner import CatchupPlanner


def test_no_last_event_generates_initial_trace():
    now = datetime(2026, 6, 15, 12, 0, 0)

    decision = CatchupPlanner.plan(None, now)

    assert decision.due is True
    assert decision.count == 1
    assert decision.reason == "initial"


def test_recent_event_is_not_due():
    now = datetime(2026, 6, 15, 12, 0, 0)
    last = now - timedelta(hours=2)

    decision = CatchupPlanner.plan(last, now)

    assert decision.due is False
    assert decision.count == 0
    assert decision.reason == "cooldown"


def test_regular_advance_after_six_hours():
    now = datetime(2026, 6, 15, 12, 0, 0)
    last = now - timedelta(hours=7)

    decision = CatchupPlanner.plan(last, now)

    assert decision.due is True
    assert decision.count == 1
    assert decision.reason == "regular"


def test_catchup_after_multiple_days_caps_at_three():
    now = datetime(2026, 6, 15, 12, 0, 0)
    last = now - timedelta(days=6)

    decision = CatchupPlanner.plan(last, now)

    assert decision.due is True
    assert decision.count == 3
    assert decision.reason == "catchup"
