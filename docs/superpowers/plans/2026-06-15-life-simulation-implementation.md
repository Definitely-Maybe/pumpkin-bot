# Life Simulation Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the v0.2 MVP life simulation layer so Nan Gua has low-key daily life events that can be naturally, sparingly shared in conversation.

**Architecture:** Add focused modules under `src/simulation/` for event generation, scheduling, context selection, sharing policy, and receptivity. Keep the existing `life_events` table and wrap `src/social/` as one optional life-event source. Integrate by reading life events in `ContextAssembler`, advancing life after postprocess through `LifeScheduler.maybe_advance()`, and replacing coarse proactive life sharing with `LifeSharingPolicy`.

**Tech Stack:** Python 3.12, aiosqlite, pytest + pytest-asyncio, existing dataclass models and storage query helpers.

---

## Execution Setup

Before implementation, create an isolated v0.2 branch or worktree using `superpowers:using-git-worktrees`.

Recommended branch name:

```bash
git checkout -b codex/life-simulation-v0.2
```

Run the baseline tests before edits:

```bash
pytest tests/ -v --ignore=tests/test_integration.py
```

Expected result before edits:

```text
253 passed, 9 skipped
```

## File Structure

Create these files:

- `src/simulation/types.py`  
  Small dataclasses and enums used only by the simulation layer.

- `src/simulation/life_receptivity.py`  
  Pure rules for estimating whether the user welcomes Nan Gua life sharing.

- `src/simulation/life_context_selector.py`  
  Pure selector and formatter that chooses 0 or 1 existing life event for prompt injection.

- `src/simulation/catchup_planner.py`  
  Pure due/catchup planner. It decides whether life should advance and how many events to create.

- `src/simulation/life_generator.py`  
  Deterministic, no-API MVP generator for non-social events.

- `src/simulation/social_scheduler_adapter.py`  
  Thin wrapper around existing `src.social.scheduler.Scheduler`.

- `src/simulation/life_scheduler.py`  
  DB-backed orchestrator for `maybe_advance()`.

- `src/simulation/life_sharing_policy.py`  
  Pure scoring and selection logic for proactive life sharing.

Modify these files:

- `src/storage/queries.py`  
  Add life-event query helpers and typed proactive count helpers.

- `src/core/context.py`  
  Read recent life events and inject optional life context.

- `src/core/postprocess.py`  
  Replace direct social tick with life scheduler, and use life sharing policy in proactive generation.

Add these tests:

- `tests/test_life_receptivity.py`
- `tests/test_life_context_selector.py`
- `tests/test_catchup_planner.py`
- `tests/test_life_generator.py`
- `tests/test_life_scheduler.py`
- `tests/test_life_sharing_policy.py`
- `tests/test_life_context_integration.py`
- `tests/test_life_proactive_integration.py`

---

### Task 1: Storage Query Helpers

**Files:**
- Modify: `src/storage/queries.py`
- Test: `tests/test_storage_queries.py`

- [ ] **Step 1: Write failing tests for life-event helpers**

Append these tests to `tests/test_storage_queries.py`:

```python
from datetime import datetime, timedelta

from src.storage.models import LifeEvent, TriggerType


@pytest.mark.asyncio
async def test_get_latest_life_event_returns_newest(tmp_path):
    conn = await init_db(tmp_path / "life-latest.db")
    try:
        older = (datetime.now() - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
        newer = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        await q.insert_life_event(conn, LifeEvent(
            event_type="life",
            category="daily",
            description="早一点的事",
            created_at=older,
        ))
        await q.insert_life_event(conn, LifeEvent(
            event_type="life",
            category="body_state",
            description="新的事",
            created_at=newer,
        ))

        latest = await q.get_latest_life_event(conn)

        assert latest is not None
        assert latest["description"] == "新的事"
        assert latest["category"] == "body_state"
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_get_recent_life_events_for_user_filters_shared(tmp_path):
    conn = await init_db(tmp_path / "life-unshared.db")
    try:
        shared = await q.insert_life_event(conn, LifeEvent(
            event_type="life",
            category="daily",
            description="已经讲过的事",
        ))
        await q.mark_event_shared(conn, shared.event_id, "u1")
        await q.insert_life_event(conn, LifeEvent(
            event_type="life",
            category="daily",
            description="还没讲过的事",
        ))

        events = await q.get_recent_life_events_for_user(conn, "u1", limit=10, unshared_only=True)

        assert [e["description"] for e in events] == ["还没讲过的事"]
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_count_proactive_today_by_types(tmp_path):
    conn = await init_db(tmp_path / "proactive-types.db")
    try:
        await q.enqueue_proactive(conn, "u1", TriggerType.LIFE_STORY, "生活分享")
        task_id = await q.enqueue_proactive(conn, "u1", TriggerType.MEMORY_TRIGGER, "追问")
        await q.mark_proactive_sent(conn, 1)
        await q.mark_proactive_sent(conn, task_id)

        life_count = await q.count_proactive_today_by_types(
            conn,
            "u1",
            [TriggerType.LIFE_STORY, TriggerType.SOCIAL_SHARE],
        )

        assert life_count == 1
    finally:
        await conn.close()
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
pytest tests/test_storage_queries.py -v
```

Expected: the new tests fail because `get_latest_life_event`, `get_recent_life_events_for_user`, and `count_proactive_today_by_types` do not exist.

- [ ] **Step 3: Implement storage helpers**

Add these functions to `src/storage/queries.py` after `get_recent_life_events`:

```python
async def get_latest_life_event(conn: aiosqlite.Connection) -> Optional[dict]:
    """Return the newest life event across all users."""
    cursor = await conn.execute(
        "SELECT * FROM life_events ORDER BY created_at DESC, event_id DESC LIMIT 1"
    )
    row = await cursor.fetchone()
    return dict(row) if row else None


async def get_recent_life_events_for_user(
    conn: aiosqlite.Connection,
    user_id: str,
    limit: int = 10,
    unshared_only: bool = False,
) -> list[dict]:
    """Return recent life events, optionally excluding events already shared to user."""
    if unshared_only:
        cursor = await conn.execute(
            """SELECT * FROM life_events
               WHERE shared_with_users NOT LIKE ?
               ORDER BY created_at DESC, event_id DESC LIMIT ?""",
            (f'%"{user_id}"%', limit),
        )
    else:
        cursor = await conn.execute(
            "SELECT * FROM life_events ORDER BY created_at DESC, event_id DESC LIMIT ?",
            (limit,),
        )
    return [dict(r) for r in await cursor.fetchall()]
```

Add this function after `count_proactive_today`:

```python
async def count_proactive_today_by_types(
    conn: aiosqlite.Connection,
    user_id: str,
    trigger_types: list[TriggerType],
) -> int:
    """Count sent proactive messages for a user today by trigger type."""
    if not trigger_types:
        return 0
    today = datetime.now().strftime("%Y-%m-%d")
    placeholders = ",".join("?" for _ in trigger_types)
    values = [user_id, today, *(t.value for t in trigger_types)]
    cursor = await conn.execute(
        f"""SELECT COUNT(*) as cnt FROM proactive_queue
            WHERE user_id = ?
            AND date(created_at) = ?
            AND status = 'sent'
            AND trigger_type IN ({placeholders})""",
        values,
    )
    row = await cursor.fetchone()
    return row["cnt"] if row else 0
```

- [ ] **Step 4: Run storage tests**

Run:

```bash
pytest tests/test_storage_queries.py -v
```

Expected: all tests in `tests/test_storage_queries.py` pass.

- [ ] **Step 5: Commit**

```bash
git add src/storage/queries.py tests/test_storage_queries.py
git commit -m "feat: add life event storage helpers"
```

---

### Task 2: Life Receptivity Rules

**Files:**
- Create: `src/simulation/types.py`
- Create: `src/simulation/life_receptivity.py`
- Test: `tests/test_life_receptivity.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_life_receptivity.py`:

```python
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
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
pytest tests/test_life_receptivity.py -v
```

Expected: import fails because the files do not exist.

- [ ] **Step 3: Add shared simulation types**

Create `src/simulation/types.py`:

```python
"""Small value types for Nan Gua life simulation."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class LifeEventKind(str, Enum):
    DAILY = "daily"
    CREATIVE = "creative"
    BODY_STATE = "body_state"
    REFLECTION = "reflection"
    SOCIAL = "social"


class ShareLevel(str, Enum):
    PUBLIC = "public"
    CASUAL = "casual"
    PERSONAL = "personal"
    VULNERABLE = "vulnerable"


@dataclass
class ReceptivityResult:
    score: float = 0.5
    label: str = "neutral"
    positive_hits: list[str] = field(default_factory=list)
    negative_hits: list[str] = field(default_factory=list)


@dataclass
class CatchupDecision:
    due: bool
    count: int = 0
    reason: str = "not_due"


@dataclass
class LifeContextCandidate:
    event_id: Optional[int]
    description: str
    category: str
    event_type: str
    share_level: ShareLevel
    score: float
```

- [ ] **Step 4: Implement receptivity estimator**

Create `src/simulation/life_receptivity.py`:

```python
"""Estimate whether a user welcomes Nan Gua's life sharing."""

from .types import ReceptivityResult


class LifeReceptivity:
    """Rule-based receptivity estimator.

    The score is intentionally conservative. It is a nudge for context and
    proactive policy, not a relationship state replacement.
    """

    _POSITIVE_SIGNALS: dict[str, list[str]] = {
        "follow_up": ["后来呢", "然后呢", "怎么样了", "后续呢"],
        "care": ["你还好吗", "别太累", "休息一下", "照顾好自己"],
        "advice": ["你可以", "要不要试试", "我觉得你可以", "不如"],
        "banter": ["哈哈", "笑死", "你也这样", "太真实了"],
        "asks_about_ng": ["你今天干嘛", "你最近怎么样", "你呢", "你在干嘛"],
    }
    _NEGATIVE_SIGNALS: dict[str, list[str]] = {
        "explicit_refusal": ["不想听这个", "别说这个", "先说我的事"],
        "dismissive": ["哦", "嗯", "行吧", "随便"],
        "topic_shift": ["算了先不说这个", "换个话题", "说正事"],
    }

    @classmethod
    def estimate(cls, messages: list[dict[str, str]], window: int = 8) -> ReceptivityResult:
        user_messages = [
            m.get("content", "")
            for m in messages[-window:]
            if m.get("role") == "user"
        ]
        if not user_messages:
            return ReceptivityResult()

        positive: list[str] = []
        negative: list[str] = []
        score = 0.5

        for idx, text in enumerate(user_messages):
            recency_weight = 1.0 + (idx / max(len(user_messages), 1))
            for label, keywords in cls._POSITIVE_SIGNALS.items():
                if any(k in text for k in keywords):
                    if label not in positive:
                        positive.append(label)
                    score += 0.12 * recency_weight
            for label, keywords in cls._NEGATIVE_SIGNALS.items():
                if any(k in text for k in keywords):
                    if label not in negative:
                        negative.append(label)
                    score -= 0.18 * recency_weight

        score = round(max(0.0, min(1.0, score)), 2)
        if score >= 0.65:
            label = "high"
        elif score <= 0.4:
            label = "low"
        else:
            label = "neutral"

        return ReceptivityResult(
            score=score,
            label=label,
            positive_hits=positive,
            negative_hits=negative,
        )
```

- [ ] **Step 5: Run receptivity tests**

Run:

```bash
pytest tests/test_life_receptivity.py -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/simulation/types.py src/simulation/life_receptivity.py tests/test_life_receptivity.py
git commit -m "feat: estimate life share receptivity"
```

---

### Task 3: Life Context Selector

**Files:**
- Create: `src/simulation/life_context_selector.py`
- Test: `tests/test_life_context_selector.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_life_context_selector.py`:

```python
from src.simulation.life_context_selector import LifeContextSelector
from src.storage.models import RelationshipType, User
from src.simulation.types import ReceptivityResult


def make_user(rel=RelationshipType.TRUSTED):
    return User(
        user_id="u1",
        platform="terminal",
        relationship_type=rel,
        familiarity_score=0.7,
        interaction_count=80,
    )


def test_selector_returns_none_when_no_events():
    selector = LifeContextSelector()

    result = selector.select(
        user=make_user(),
        user_message="今天好累",
        events=[],
        receptivity=ReceptivityResult(score=0.7, label="high"),
    )

    assert result is None


def test_selector_picks_related_body_state_event_for_tired_user():
    selector = LifeContextSelector()
    events = [
        {"event_id": 1, "event_type": "life", "category": "daily", "description": "上午去买水。", "shared_with_users": "[]"},
        {"event_id": 2, "event_type": "life", "category": "body_state", "description": "下午有点低电量，坐着放空了十分钟。", "shared_with_users": "[]"},
    ]

    result = selector.select(
        user=make_user(),
        user_message="今天好累，完全没电了",
        events=events,
        receptivity=ReceptivityResult(score=0.7, label="high"),
    )

    assert result is not None
    assert result.event_id == 2
    assert result.category == "body_state"


def test_selector_blocks_personal_event_for_stranger():
    selector = LifeContextSelector()
    events = [
        {"event_id": 2, "event_type": "life", "category": "reflection", "description": "深夜突然有点自我怀疑。", "shared_with_users": "[]"},
    ]

    result = selector.select(
        user=make_user(RelationshipType.STRANGER),
        user_message="你最近怎么样",
        events=events,
        receptivity=ReceptivityResult(score=0.8, label="high"),
    )

    assert result is None


def test_selector_blocks_when_user_is_in_strong_distress():
    selector = LifeContextSelector()
    events = [
        {"event_id": 2, "event_type": "life", "category": "body_state", "description": "下午低电量。", "shared_with_users": "[]"},
    ]

    result = selector.select(
        user=make_user(),
        user_message="我真的崩溃了，今天很难受，不知道怎么办",
        events=events,
        receptivity=ReceptivityResult(score=0.8, label="high"),
    )

    assert result is None


def test_format_prompt_context_uses_optional_language():
    selector = LifeContextSelector()
    candidate = selector.select(
        user=make_user(),
        user_message="今天好累",
        events=[
            {"event_id": 2, "event_type": "life", "category": "body_state", "description": "下午有点低电量。", "shared_with_users": "[]"},
        ],
        receptivity=ReceptivityResult(score=0.8, label="high"),
    )

    text = selector.format_for_prompt(candidate)

    assert "如果自然相关" in text
    assert "完全不要提" in text
    assert "不要解释这是记忆、事件或系统记录" in text
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
pytest tests/test_life_context_selector.py -v
```

Expected: import fails because `life_context_selector.py` does not exist.

- [ ] **Step 3: Implement selector**

Create `src/simulation/life_context_selector.py`:

```python
"""Select one existing life event that may be naturally mentioned in prompt."""

import json

from ..storage.models import RelationshipType, User
from .types import LifeContextCandidate, ReceptivityResult, ShareLevel


class LifeContextSelector:
    """Choose at most one life event for optional prompt injection."""

    _DISTRESS_WORDS = ["崩溃", "难受", "痛苦", "不想活", "怎么办", "撑不住"]
    _TOPIC_KEYWORDS: dict[str, list[str]] = {
        "body_state": ["累", "困", "没电", "低电量", "熬夜", "睡"],
        "creative": ["代码", "项目", "prompt", "bot", "卡住", "灵感"],
        "reflection": ["想法", "反思", "焦虑", "自我", "深夜"],
        "daily": ["吃", "出门", "散步", "天气", "上课", "日常"],
        "social": ["朋友", "同学", "wtt", "ccx", "mxt", "mcyy", "颜姐"],
    }
    _RELATION_ALLOWED_LEVELS: dict[RelationshipType, set[ShareLevel]] = {
        RelationshipType.STRANGER: {ShareLevel.PUBLIC},
        RelationshipType.ACQUAINTANCE: {ShareLevel.PUBLIC, ShareLevel.CASUAL},
        RelationshipType.TRUSTED: {ShareLevel.PUBLIC, ShareLevel.CASUAL, ShareLevel.PERSONAL},
        RelationshipType.BROTHER: {ShareLevel.PUBLIC, ShareLevel.CASUAL, ShareLevel.PERSONAL},
        RelationshipType.RESPECTED: {ShareLevel.PUBLIC, ShareLevel.CASUAL, ShareLevel.PERSONAL, ShareLevel.VULNERABLE},
        RelationshipType.CRUSH: {ShareLevel.PUBLIC, ShareLevel.CASUAL, ShareLevel.PERSONAL, ShareLevel.VULNERABLE},
    }

    def select(
        self,
        user: User,
        user_message: str,
        events: list[dict],
        receptivity: ReceptivityResult,
    ) -> LifeContextCandidate | None:
        if not events:
            return None
        if self._strong_distress(user_message):
            return None
        if receptivity.label == "low":
            return None

        best: LifeContextCandidate | None = None
        for event in events:
            if self._is_shared(event, user.user_id):
                continue
            share_level = self.classify_share_level(event)
            allowed = self._RELATION_ALLOWED_LEVELS.get(user.relationship_type, {ShareLevel.PUBLIC})
            if share_level not in allowed:
                continue
            score = self._score_event(user_message, event, receptivity)
            if score < 0.45:
                continue
            candidate = LifeContextCandidate(
                event_id=event.get("event_id"),
                description=event.get("description", ""),
                category=event.get("category", ""),
                event_type=event.get("event_type", ""),
                share_level=share_level,
                score=score,
            )
            if best is None or candidate.score > best.score:
                best = candidate
        return best

    def format_for_prompt(self, candidate: LifeContextCandidate | None) -> str:
        if candidate is None:
            return ""
        return (
            "## 南瓜最近可联想到的一件生活小事\n"
            f"- {candidate.description}\n\n"
            "如果自然相关，可以像朋友顺手一提；如果不贴合当前话题，就完全不要提。\n"
            "不要解释这是记忆、事件或系统记录。\n"
            "提到后要回到用户，不要展开成南瓜独白。"
        )

    @classmethod
    def classify_share_level(cls, event: dict) -> ShareLevel:
        category = event.get("category", "")
        description = event.get("description", "")
        if category == "reflection":
            return ShareLevel.VULNERABLE
        if category == "body_state" or any(w in description for w in ["低电量", "焦虑", "自我怀疑"]):
            return ShareLevel.PERSONAL
        if category in ("creative", "social"):
            return ShareLevel.CASUAL
        return ShareLevel.PUBLIC

    @classmethod
    def _strong_distress(cls, text: str) -> bool:
        return any(word in text for word in cls._DISTRESS_WORDS)

    @classmethod
    def _is_shared(cls, event: dict, user_id: str) -> bool:
        raw = event.get("shared_with_users") or "[]"
        try:
            shared = json.loads(raw)
        except json.JSONDecodeError:
            return False
        return user_id in shared

    @classmethod
    def _score_event(cls, user_message: str, event: dict, receptivity: ReceptivityResult) -> float:
        category = event.get("category", "")
        description = event.get("description", "")
        score = 0.15 + (receptivity.score * 0.25)

        for keyword in cls._TOPIC_KEYWORDS.get(category, []):
            if keyword.lower() in user_message.lower() or keyword.lower() in description.lower():
                score += 0.2

        for keyword in ["累", "困", "没电", "低电量"]:
            if keyword in user_message and keyword in description:
                score += 0.25

        if "?" in user_message or "？" in user_message or "你最近" in user_message or "你今天" in user_message:
            score += 0.15

        return round(min(1.0, score), 2)
```

- [ ] **Step 4: Run selector tests**

Run:

```bash
pytest tests/test_life_context_selector.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/simulation/life_context_selector.py tests/test_life_context_selector.py
git commit -m "feat: select optional life context"
```

---

### Task 4: Catchup Planner

**Files:**
- Create: `src/simulation/catchup_planner.py`
- Test: `tests/test_catchup_planner.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_catchup_planner.py`:

```python
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
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
pytest tests/test_catchup_planner.py -v
```

Expected: import fails because `catchup_planner.py` does not exist.

- [ ] **Step 3: Implement catchup planner**

Create `src/simulation/catchup_planner.py`:

```python
"""Decide whether Nan Gua's life should advance."""

from datetime import datetime, timedelta

from .types import CatchupDecision


class CatchupPlanner:
    """Pure due/catchup planner for life simulation."""

    REGULAR_INTERVAL = timedelta(hours=6)
    CATCHUP_THRESHOLD = timedelta(days=2)
    MAX_CATCHUP_EVENTS = 3

    @classmethod
    def plan(cls, last_event_at: datetime | None, now: datetime) -> CatchupDecision:
        if last_event_at is None:
            return CatchupDecision(due=True, count=1, reason="initial")

        elapsed = now - last_event_at
        if elapsed < cls.REGULAR_INTERVAL:
            return CatchupDecision(due=False, count=0, reason="cooldown")

        if elapsed >= cls.CATCHUP_THRESHOLD:
            days = max(1, elapsed.days)
            return CatchupDecision(
                due=True,
                count=min(cls.MAX_CATCHUP_EVENTS, days),
                reason="catchup",
            )

        return CatchupDecision(due=True, count=1, reason="regular")
```

- [ ] **Step 4: Run planner tests**

Run:

```bash
pytest tests/test_catchup_planner.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/simulation/catchup_planner.py tests/test_catchup_planner.py
git commit -m "feat: plan life event catchup"
```

---

### Task 5: Non-Social Life Generator

**Files:**
- Create: `src/simulation/life_generator.py`
- Test: `tests/test_life_generator.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_life_generator.py`:

```python
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
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
pytest tests/test_life_generator.py -v
```

Expected: import fails because `life_generator.py` does not exist.

- [ ] **Step 3: Implement generator**

Create `src/simulation/life_generator.py`:

```python
"""Generate low-key non-social life events without calling an LLM."""

import random
from datetime import datetime

from ..storage.models import LifeEvent


class LifeGenerator:
    """MVP template generator for Nan Gua daily life traces."""

    _DAY_WEIGHTS = [
        ("daily", 60),
        ("creative", 12),
        ("body_state", 15),
        ("reflection", 8),
    ]
    _NIGHT_WEIGHTS = [
        ("daily", 35),
        ("creative", 8),
        ("body_state", 32),
        ("reflection", 25),
    ]
    _TEMPLATES: dict[str, list[tuple[str, str]]] = {
        "daily": [
            ("下午出门买水，路上有点放空，回来才发现自己走得很慢。", "calm"),
            ("吃饭的时候刷了会儿手机，没刷到什么有意思的，倒是把时间刷没了。", "neutral"),
            ("本来想收拾一下桌子，结果只把杯子挪了个位置。", "neutral"),
            ("路过楼下的时候吹了会儿风，脑子稍微清醒了一点。", "calm"),
        ],
        "creative": [
            ("写东西写到一半卡住了，后来只记下一句很粗糙的想法。", "focused"),
            ("看着项目文件发了会儿呆，突然觉得有个小结构可以拆得更干净。", "focused"),
            ("本来想推进一点 bot 的逻辑，结果先被一个命名问题绊住了。", "neutral"),
        ],
        "body_state": [
            ("下午有点低电量，坐着放空了十分钟。", "tired"),
            ("昨晚睡得不算踏实，今天反应慢半拍。", "tired"),
            ("晚一点的时候整个人缓过来了一点，没有下午那么钝。", "calm"),
        ],
        "reflection": [
            ("深夜的时候突然想起自己最近有点用力过猛，心里安静了一会儿。", "reflective"),
            ("洗完澡后脑子松下来，意识到有些事不用立刻想明白。", "reflective"),
            ("晚上有一小段时间很想逃开消息，但后来又觉得这不算坏事。", "reflective"),
        ],
    }

    def __init__(self, rng: random.Random | None = None):
        self.rng = rng or random.Random()

    def generate(self, now: datetime | None = None, reason: str = "regular") -> LifeEvent:
        now = now or datetime.now()
        category = self._choose_category(now)
        description, emotion = self.rng.choice(self._TEMPLATES[category])
        if reason == "catchup":
            description = self._soften_for_catchup(description)
        return LifeEvent(
            event_type="life",
            category=category,
            description=description,
            characters_involved="[]",
            emotion=emotion,
            causality_chain_id=None,
            created_at=now.strftime("%Y-%m-%d %H:%M:%S"),
        )

    def _choose_category(self, now: datetime) -> str:
        weights = self._NIGHT_WEIGHTS if now.hour >= 22 or now.hour <= 2 else self._DAY_WEIGHTS
        categories = [c for c, _ in weights]
        values = [w for _, w in weights]
        return self.rng.choices(categories, weights=values, k=1)[0]

    @staticmethod
    def _soften_for_catchup(description: str) -> str:
        replacements = {
            "下午": "前阵子有一会儿",
            "晚一点的时候": "后来某个时候",
            "昨晚": "有天晚上",
            "深夜的时候": "有天深夜",
        }
        for old, new in replacements.items():
            description = description.replace(old, new)
        return description
```

- [ ] **Step 4: Run generator tests**

Run:

```bash
pytest tests/test_life_generator.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/simulation/life_generator.py tests/test_life_generator.py
git commit -m "feat: generate non-social life events"
```

---

### Task 6: Life Scheduler and Social Adapter

**Files:**
- Create: `src/simulation/social_scheduler_adapter.py`
- Create: `src/simulation/life_scheduler.py`
- Test: `tests/test_life_scheduler.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_life_scheduler.py`:

```python
from datetime import datetime, timedelta

import pytest

from src.simulation.life_scheduler import LifeScheduler
from src.storage.db import init_db
from src.storage.models import LifeEvent
from src.storage import queries as q


@pytest.mark.asyncio
async def test_maybe_advance_creates_initial_event(tmp_path):
    conn = await init_db(tmp_path / "life-scheduler-initial.db")
    try:
        scheduler = LifeScheduler(conn)

        events = await scheduler.maybe_advance(now=datetime(2026, 6, 15, 12, 0, 0))

        assert len(events) == 1
        stored = await q.get_recent_life_events(conn, limit=5)
        assert len(stored) == 1
        assert stored[0]["event_type"] == "life"
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_maybe_advance_recent_event_returns_zero(tmp_path):
    conn = await init_db(tmp_path / "life-scheduler-cooldown.db")
    try:
        now = datetime(2026, 6, 15, 12, 0, 0)
        await q.insert_life_event(conn, LifeEvent(
            event_type="life",
            category="daily",
            description="刚刚发生过",
            created_at=(now - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S"),
        ))
        scheduler = LifeScheduler(conn)

        events = await scheduler.maybe_advance(now=now)

        assert events == []
        stored = await q.get_recent_life_events(conn, limit=5)
        assert len(stored) == 1
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_maybe_advance_catchup_caps_at_three(tmp_path):
    conn = await init_db(tmp_path / "life-scheduler-catchup.db")
    try:
        now = datetime(2026, 6, 15, 12, 0, 0)
        await q.insert_life_event(conn, LifeEvent(
            event_type="life",
            category="daily",
            description="很久以前",
            created_at=(now - timedelta(days=5)).strftime("%Y-%m-%d %H:%M:%S"),
        ))
        scheduler = LifeScheduler(conn)

        events = await scheduler.maybe_advance(now=now)

        assert len(events) == 3
        stored = await q.get_recent_life_events(conn, limit=10)
        assert len(stored) == 4
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_social_adapter_failure_does_not_block_life_generation(tmp_path):
    conn = await init_db(tmp_path / "life-scheduler-social-fail.db")
    try:
        now = datetime(2026, 6, 15, 12, 0, 0)
        await q.insert_life_event(conn, LifeEvent(
            event_type="life",
            category="daily",
            description="上一次生活事件",
            created_at=(now - timedelta(hours=7)).strftime("%Y-%m-%d %H:%M:%S"),
        ))

        class FailingAdapter:
            async def maybe_advance(self, user_message="", diagnostics=None):
                raise RuntimeError("social failed")

        scheduler = LifeScheduler(conn, social_adapter=FailingAdapter())

        events = await scheduler.maybe_advance(now=now, user_message="wtt 最近怎么样")

        assert len(events) == 1
        stored = await q.get_recent_life_events(conn, limit=10)
        assert len(stored) == 2
    finally:
        await conn.close()
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
pytest tests/test_life_scheduler.py -v
```

Expected: import fails because `life_scheduler.py` does not exist.

- [ ] **Step 3: Implement social adapter**

Create `src/simulation/social_scheduler_adapter.py`:

```python
"""Adapter that lets the life layer reuse the existing social scheduler."""

import aiosqlite


class SocialSchedulerAdapter:
    """Thin wrapper around src.social.scheduler.Scheduler."""

    def __init__(self, db: aiosqlite.Connection, llm=None, system_prompt: str = ""):
        from ..social.scheduler import Scheduler

        self.scheduler = Scheduler(db, llm, system_prompt=system_prompt)

    async def maybe_advance(self, user_message: str = "", diagnostics: dict | None = None) -> list[dict]:
        return await self.scheduler.tick(user_message=user_message, diagnostics=diagnostics)
```

- [ ] **Step 4: Implement life scheduler**

Create `src/simulation/life_scheduler.py`:

```python
"""DB-backed life simulation scheduler."""

from datetime import datetime

import aiosqlite

from .catchup_planner import CatchupPlanner
from .life_generator import LifeGenerator
from .social_scheduler_adapter import SocialSchedulerAdapter
from ..storage import queries as q
from ..storage.models import LifeEvent


class LifeScheduler:
    """Advance Nan Gua's life when due.

    Being called does not mean an event is generated. The catchup planner is
    the gate.
    """

    def __init__(
        self,
        db: aiosqlite.Connection,
        llm=None,
        generator: LifeGenerator | None = None,
        social_adapter=None,
    ):
        self.db = db
        self.generator = generator or LifeGenerator()
        self.social_adapter = social_adapter or SocialSchedulerAdapter(db, llm)

    async def maybe_advance(
        self,
        user_message: str = "",
        now: datetime | None = None,
        diagnostics: dict | None = None,
    ) -> list[dict]:
        now = now or datetime.now()
        latest = await q.get_latest_life_event(self.db)
        last_at = self._parse_time(latest.get("created_at")) if latest else None
        decision = CatchupPlanner.plan(last_at, now)

        if diagnostics is not None:
            diagnostics["life_due"] = decision.due
            diagnostics["life_reason"] = decision.reason
            diagnostics["life_count"] = decision.count

        if not decision.due:
            return []

        generated: list[dict] = []
        for _ in range(decision.count):
            event = self.generator.generate(now=now, reason=decision.reason)
            saved = await q.insert_life_event(self.db, event)
            generated.append(self._life_event_to_dict(saved))

        try:
            if self._should_try_social(user_message, decision.reason):
                social_events = await self.social_adapter.maybe_advance(
                    user_message=user_message,
                    diagnostics=diagnostics,
                )
                generated.extend(social_events)
        except Exception:
            if diagnostics is not None:
                diagnostics["social_error"] = True

        return generated

    @staticmethod
    def _parse_time(value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _should_try_social(user_message: str, reason: str) -> bool:
        if reason not in {"regular", "catchup"}:
            return False
        known_names = ["wtt", "ccx", "mxt", "mcyy", "吴田田", "蔡楚娴", "毛雪婷", "颜姐"]
        return any(name.lower() in user_message.lower() for name in known_names)

    @staticmethod
    def _life_event_to_dict(event: LifeEvent) -> dict:
        return {
            "event_id": event.event_id,
            "event_type": event.event_type,
            "category": event.category,
            "description": event.description,
            "characters_involved": event.characters_involved,
            "emotion": event.emotion,
            "causality_chain_id": event.causality_chain_id,
            "shared_with_users": event.shared_with_users,
            "created_at": event.created_at,
        }
```

- [ ] **Step 5: Run scheduler tests**

Run:

```bash
pytest tests/test_life_scheduler.py -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/simulation/social_scheduler_adapter.py src/simulation/life_scheduler.py tests/test_life_scheduler.py
git commit -m "feat: schedule life event advancement"
```

---

### Task 7: ContextAssembler Integration

**Files:**
- Modify: `src/core/context.py`
- Test: `tests/test_life_context_integration.py`

- [ ] **Step 1: Write failing integration tests**

Create `tests/test_life_context_integration.py`:

```python
from pathlib import Path

import pytest

from src.core.context import ContextAssembler
from src.core.contracts import UserSession
from src.persona.memory import SelfMemory
from src.storage.db import init_db
from src.storage.models import LifeEvent, PersonaState, RelationshipType, User
from src.storage import queries as q


def write_persona_files(tmp_path):
    persona = tmp_path / "persona.md"
    persona.write_text(
        "## Layer 0\n你是南瓜。\n## Layer 4\n关系规则\n## Layer 5\n元认知",
        encoding="utf-8",
    )
    self_md = tmp_path / "self.md"
    self_md.write_text("## 自我\n南瓜的普通生活。", encoding="utf-8")
    return persona, self_md


@pytest.mark.asyncio
async def test_context_includes_optional_life_context_when_related(tmp_path):
    conn = await init_db(tmp_path / "life-context.db")
    try:
        persona, self_md = write_persona_files(tmp_path)
        user = User(
            user_id="u1",
            platform="terminal",
            relationship_type=RelationshipType.TRUSTED,
            familiarity_score=0.8,
            interaction_count=80,
        )
        await q.upsert_user(conn, user)
        await q.insert_life_event(conn, LifeEvent(
            event_type="life",
            category="body_state",
            description="下午有点低电量，坐着放空了十分钟。",
        ))
        session = UserSession(
            user=user,
            relationship=user.relationship_type,
            persona_state=PersonaState(),
            history=[],
        )
        assembler = ContextAssembler(str(persona), SelfMemory(self_md), conn)

        ctx = await assembler.assemble(session, "今天好累，完全低电量")

        assert "南瓜最近可联想到的一件生活小事" in ctx.system_prompt
        assert "如果自然相关" in ctx.system_prompt
        assert "下午有点低电量" in ctx.system_prompt
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_context_does_not_include_life_context_for_distress(tmp_path):
    conn = await init_db(tmp_path / "life-context-distress.db")
    try:
        persona, self_md = write_persona_files(tmp_path)
        user = User(
            user_id="u1",
            platform="terminal",
            relationship_type=RelationshipType.TRUSTED,
            familiarity_score=0.8,
            interaction_count=80,
        )
        await q.upsert_user(conn, user)
        await q.insert_life_event(conn, LifeEvent(
            event_type="life",
            category="body_state",
            description="下午有点低电量。",
        ))
        session = UserSession(
            user=user,
            relationship=user.relationship_type,
            persona_state=PersonaState(),
            history=[],
        )
        assembler = ContextAssembler(str(persona), SelfMemory(self_md), conn)

        ctx = await assembler.assemble(session, "我真的崩溃了，不知道怎么办")

        assert "南瓜最近可联想到的一件生活小事" not in ctx.system_prompt
    finally:
        await conn.close()
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
pytest tests/test_life_context_integration.py -v
```

Expected: tests fail because `ContextAssembler` does not include life context.

- [ ] **Step 3: Modify ContextAssembler**

In `src/core/context.py`, add a selector import inside `assemble()` after important memories or directly before system prompt construction:

```python
        # 8. 生活事件（可选联想，最多 1 条）
        if self.db:
            try:
                from ..storage import queries as q
                from ..simulation.life_context_selector import LifeContextSelector
                from ..simulation.life_receptivity import LifeReceptivity

                events = await q.get_recent_life_events_for_user(
                    self.db,
                    session.user.user_id,
                    limit=8,
                    unshared_only=True,
                )
                receptivity = LifeReceptivity.estimate(session.history)
                selector = LifeContextSelector()
                candidate = selector.select(
                    user=session.user,
                    user_message=user_message,
                    events=events,
                    receptivity=receptivity,
                )
                life_context = selector.format_for_prompt(candidate)
                if life_context:
                    extra.append(life_context)
            except Exception:
                pass
```

Place this block after the existing important-memory block, before:

```python
        # 拼 system prompt
        system_prompt = build_system_prompt(self.layers["L0_3"], extra)
```

- [ ] **Step 4: Run context integration tests**

Run:

```bash
pytest tests/test_life_context_integration.py -v
```

Expected: both tests pass.

- [ ] **Step 5: Run existing context-adjacent tests**

Run:

```bash
pytest tests/integration/test_relationship_to_context.py tests/integration/test_memory_to_context.py -v
```

Expected: non-LLM tests pass and LLM tests skip if `DEEPSEEK_API_KEY` is absent.

- [ ] **Step 6: Commit**

```bash
git add src/core/context.py tests/test_life_context_integration.py
git commit -m "feat: inject optional life context"
```

---

### Task 8: Life Sharing Policy

**Files:**
- Create: `src/simulation/life_sharing_policy.py`
- Test: `tests/test_life_sharing_policy.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_life_sharing_policy.py`:

```python
from src.simulation.life_sharing_policy import LifeSharingPolicy
from src.simulation.types import ReceptivityResult
from src.storage.models import RelationshipType, TriggerType, User


def make_user(rel):
    return User(
        user_id="u1",
        platform="terminal",
        relationship_type=rel,
        familiarity_score=0.8,
        interaction_count=80,
    )


def test_stranger_cannot_receive_proactive_life_share():
    policy = LifeSharingPolicy()
    event = {"event_id": 1, "event_type": "life", "category": "daily", "description": "出门吹了会儿风。"}

    result = policy.select_event(
        user=make_user(RelationshipType.STRANGER),
        events=[event],
        receptivity=ReceptivityResult(score=0.9, label="high"),
        life_shares_today=0,
    )

    assert result is None


def test_low_receptivity_blocks_share():
    policy = LifeSharingPolicy()
    event = {"event_id": 1, "event_type": "life", "category": "daily", "description": "出门吹了会儿风。"}

    result = policy.select_event(
        user=make_user(RelationshipType.TRUSTED),
        events=[event],
        receptivity=ReceptivityResult(score=0.2, label="low"),
        life_shares_today=0,
    )

    assert result is None


def test_daily_limit_blocks_share():
    policy = LifeSharingPolicy()
    event = {"event_id": 1, "event_type": "life", "category": "daily", "description": "出门吹了会儿风。"}

    result = policy.select_event(
        user=make_user(RelationshipType.TRUSTED),
        events=[event],
        receptivity=ReceptivityResult(score=0.9, label="high"),
        life_shares_today=1,
    )

    assert result is None


def test_trusted_selects_high_value_event_with_context():
    policy = LifeSharingPolicy()
    events = [
        {"event_id": 1, "event_type": "life", "category": "daily", "description": "吃了个饭。"},
        {"event_id": 2, "event_type": "life", "category": "body_state", "description": "下午有点低电量，坐着放空了十分钟。"},
    ]

    result = policy.select_event(
        user=make_user(RelationshipType.TRUSTED),
        events=events,
        receptivity=ReceptivityResult(score=0.9, label="high"),
        life_shares_today=0,
    )

    assert result is not None
    assert result.event["event_id"] == 2
    assert result.trigger_type == TriggerType.LIFE_STORY
    assert "下午有点低电量" in result.context
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
pytest tests/test_life_sharing_policy.py -v
```

Expected: import fails because `life_sharing_policy.py` does not exist.

- [ ] **Step 3: Implement sharing policy**

Create `src/simulation/life_sharing_policy.py`:

```python
"""Policy for very conservative proactive life sharing."""

from dataclasses import dataclass

from ..storage.models import RelationshipType, TriggerType, User
from .life_context_selector import LifeContextSelector
from .types import ReceptivityResult, ShareLevel


@dataclass
class LifeShareDecision:
    event: dict
    trigger_type: TriggerType
    context: str
    score: float


class LifeSharingPolicy:
    """Select at most one life event for proactive sharing."""

    _ALLOWED_RELATIONSHIPS = {
        RelationshipType.TRUSTED,
        RelationshipType.BROTHER,
        RelationshipType.RESPECTED,
        RelationshipType.CRUSH,
    }

    def select_event(
        self,
        user: User,
        events: list[dict],
        receptivity: ReceptivityResult,
        life_shares_today: int,
    ) -> LifeShareDecision | None:
        if user.relationship_type not in self._ALLOWED_RELATIONSHIPS:
            return None
        if receptivity.label == "low":
            return None
        if life_shares_today >= 1:
            return None

        best: LifeShareDecision | None = None
        for event in events:
            score = self.score_event(event, receptivity)
            if score < 0.62:
                continue
            trigger = TriggerType.SOCIAL_SHARE if event.get("event_type") == "social" else TriggerType.LIFE_STORY
            context = self.format_context(event)
            decision = LifeShareDecision(event=event, trigger_type=trigger, context=context, score=score)
            if best is None or decision.score > best.score:
                best = decision
        return best

    @classmethod
    def score_event(cls, event: dict, receptivity: ReceptivityResult) -> float:
        score = receptivity.score * 0.25
        category = event.get("category", "")
        event_type = event.get("event_type", "")
        description = event.get("description", "")
        share_level = LifeContextSelector.classify_share_level(event)

        if event_type == "social":
            score += 0.25
        if category in {"body_state", "reflection"}:
            score += 0.25
        if category == "creative":
            score += 0.18
        if category == "daily":
            score += 0.12
        if share_level in {ShareLevel.PERSONAL, ShareLevel.VULNERABLE}:
            score += 0.16
        if any(word in description for word in ["低电量", "想明白", "好笑", "奇怪", "卡住"]):
            score += 0.16

        return round(min(1.0, score), 2)

    @staticmethod
    def format_context(event: dict) -> str:
        return (
            "这是一条可主动分享的南瓜近况。必须短、自然、克制；"
            "不要像日报，不要解释系统记录。近况："
            f"{event.get('description', '')}"
        )
```

- [ ] **Step 4: Run policy tests**

Run:

```bash
pytest tests/test_life_sharing_policy.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/simulation/life_sharing_policy.py tests/test_life_sharing_policy.py
git commit -m "feat: add conservative life sharing policy"
```

---

### Task 9: Proactive Life Sharing Integration

**Files:**
- Modify: `src/core/postprocess.py`
- Test: `tests/test_life_proactive_integration.py`

- [ ] **Step 1: Write failing integration tests**

Create `tests/test_life_proactive_integration.py`:

```python
import pytest

from src.core.contracts import UserSession
from src.core.postprocess import PostProcessor
from src.storage.db import init_db
from src.storage.models import LifeEvent, PersonaState, RelationshipType, TriggerType, User
from src.storage import queries as q


class FakeLLM:
    async def generate_proactive(self, user_name, trigger_type, context, system_prompt, relationship_type):
        assert "近况" in context
        return f"主动分享:{trigger_type}:{relationship_type}"


def make_session(user):
    return UserSession(
        user=user,
        relationship=user.relationship_type,
        persona_state=PersonaState(),
        history=[{"role": "user", "content": "后来呢？你还好吗？"}],
    )


@pytest.mark.asyncio
async def test_life_share_policy_marks_event_shared_after_send(tmp_path):
    conn = await init_db(tmp_path / "life-proactive.db")
    sent = []

    async def sender(user_id, messages):
        sent.extend(messages)
        return True

    try:
        user = User(
            user_id="u1",
            platform="terminal",
            relationship_type=RelationshipType.TRUSTED,
            familiarity_score=0.8,
            interaction_count=80,
        )
        await q.upsert_user(conn, user)
        event = await q.insert_life_event(conn, LifeEvent(
            event_type="life",
            category="body_state",
            description="下午有点低电量，坐着放空了十分钟。",
        ))
        pp = PostProcessor(conn, llm=FakeLLM(), proactive_sender=sender)

        await pp._check_proactive_triggers(make_session(user), system_prompt="你是南瓜。")

        assert sent == ["主动分享:life_story:trusted"]
        refreshed = await q.get_recent_life_events_for_user(conn, "u1", limit=5, unshared_only=False)
        shared_event = next(e for e in refreshed if e["event_id"] == event.event_id)
        assert '"u1"' in shared_event["shared_with_users"]
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_low_receptivity_does_not_share_life_event(tmp_path):
    conn = await init_db(tmp_path / "life-proactive-low.db")
    sent = []

    async def sender(user_id, messages):
        sent.extend(messages)
        return True

    try:
        user = User(
            user_id="u1",
            platform="terminal",
            relationship_type=RelationshipType.TRUSTED,
            familiarity_score=0.8,
            interaction_count=80,
        )
        await q.upsert_user(conn, user)
        await q.insert_life_event(conn, LifeEvent(
            event_type="life",
            category="body_state",
            description="下午有点低电量，坐着放空了十分钟。",
        ))
        pp = PostProcessor(conn, llm=FakeLLM(), proactive_sender=sender)
        session = UserSession(
            user=user,
            relationship=user.relationship_type,
            persona_state=PersonaState(),
            history=[{"role": "user", "content": "不想听这个，先说我的事。"}],
        )

        await pp._check_proactive_triggers(session, system_prompt="你是南瓜。")

        assert sent == []
    finally:
        await conn.close()
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
pytest tests/test_life_proactive_integration.py -v
```

Expected: first test fails because current proactive flow does not mark the life event as shared and does not pass event context.

- [ ] **Step 3: Modify `_check_proactive_triggers`**

In `src/core/postprocess.py`, after loading `unshared`, compute life sharing decision:

```python
        life_share_decision = None
        try:
            from ..simulation.life_receptivity import LifeReceptivity
            from ..simulation.life_sharing_policy import LifeSharingPolicy

            life_share_count = await q.count_proactive_today_by_types(
                self.db,
                user.user_id,
                [TriggerType.LIFE_STORY, TriggerType.SOCIAL_SHARE],
            )
            receptivity = LifeReceptivity.estimate(session.history)
            life_share_decision = LifeSharingPolicy().select_event(
                user=user,
                events=unshared,
                receptivity=receptivity,
                life_shares_today=life_share_count,
            )
        except Exception:
            life_share_decision = None
```

Before calling `TriggerManager.check_all`, create the event list passed to old trigger checks:

```python
        trigger_unshared = [life_share_decision.event] if life_share_decision else []
```

Then change the `TriggerManager.check_all` call to:

```python
            unshared_events=trigger_unshared,
```

Inside the generation loop, replace:

```python
            extra_context = context or ""
```

with:

```python
            extra_context = context or ""
            selected_life_event_id = None
            if life_share_decision and trigger_type == life_share_decision.trigger_type:
                extra_context = life_share_decision.context
                selected_life_event_id = life_share_decision.event.get("event_id")
```

After successful send/queue handling, add:

```python
                    if selected_life_event_id:
                        await q.mark_event_shared(
                            self.db,
                            selected_life_event_id,
                            user.user_id,
                        )
```

Place that block inside `if msg:` after optional runtime send handling, before milestone dedupe.

- [ ] **Step 4: Run proactive integration tests**

Run:

```bash
pytest tests/test_life_proactive_integration.py -v
```

Expected: both tests pass.

- [ ] **Step 5: Run existing proactive tests**

Run:

```bash
pytest tests/test_trigger_manager.py tests/test_proactive_integration.py tests/test_postprocess_regressions.py -v
```

Expected: all tests pass. If a legacy test expected any daily event to trigger, update the expectation to match the new conservative policy only when that test constructs a trusted user, positive receptivity history, and a high-value event.

- [ ] **Step 6: Commit**

```bash
git add src/core/postprocess.py tests/test_life_proactive_integration.py
git commit -m "feat: gate proactive life sharing"
```

---

### Task 10: PostProcessor Life Scheduler Integration

**Files:**
- Modify: `src/core/postprocess.py`
- Test: `tests/test_postprocess_regressions.py`

- [ ] **Step 1: Write failing regression test**

Append this test to `tests/test_postprocess_regressions.py`:

```python
@pytest.mark.asyncio
async def test_life_tick_does_not_generate_every_turn_when_recent_event_exists(db):
    from datetime import datetime
    from src.storage.models import LifeEvent, RelationshipType, User, PersonaState
    from src.core.contracts import UserSession
    from src.storage import queries as q

    user = User(
        user_id="life-tick-user",
        platform="terminal",
        relationship_type=RelationshipType.TRUSTED,
        interaction_count=80,
    )
    await q.upsert_user(db, user)
    await q.insert_life_event(db, LifeEvent(
        event_type="life",
        category="daily",
        description="刚刚发生过的生活事件",
        created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    ))
    session = UserSession(
        user=user,
        relationship=user.relationship_type,
        persona_state=PersonaState(),
        history=[],
    )
    pp = PostProcessor(db, llm=object())

    await pp._life_tick(session, user_message="普通聊天")

    events = await q.get_recent_life_events(db, limit=5)
    assert len(events) == 1
```

- [ ] **Step 2: Run test and verify it fails**

Run:

```bash
pytest tests/test_postprocess_regressions.py::test_life_tick_does_not_generate_every_turn_when_recent_event_exists -v
```

Expected: test fails because `_life_tick` does not exist.

- [ ] **Step 3: Replace social tick call with life tick**

In `src/core/postprocess.py`, replace this block in `run_sidecars`:

```python
        # 9. 社交模拟 tick（后台生成社交事件）
        await self._social_tick(session, incoming_text)
```

with:

```python
        # 9. 生活模拟 maybe_advance（用户消息只是检查机会，不保证生成）
        await self._life_tick(session, incoming_text)
```

Add this method above the existing `_social_tick` method:

```python
    async def _life_tick(self, session: UserSession, user_message: str):
        """生活模拟：按冷却/节律推进生活事件。失败不阻塞 pipeline。"""
        if not self.llm:
            return
        diag: dict = {}
        events = []
        try:
            from ..simulation.life_scheduler import LifeScheduler
            if not hasattr(self, '_life_scheduler'):
                self._life_scheduler = LifeScheduler(self.db, self.llm)
            events = await self._life_scheduler.maybe_advance(
                user_message=user_message,
                diagnostics=diag,
            )
        except Exception:
            events = []

        if hasattr(self, '_debug') and self._debug:
            due = diag.get("life_due", False)
            reason = diag.get("life_reason", "not_due")
            count = len(events)
            if count:
                preview = "\n".join(
                    f"- {e.get('description', '')[:100]}"
                    for e in events[:3]
                )
                self._debug.sidecar(
                    9,
                    "🌿",
                    "生活模拟",
                    f"推进 {count} 条（reason={reason}）\n{preview}",
                )
            else:
                self._debug.sidecar(
                    9,
                    "⏭️",
                    "生活模拟",
                    f"未推进（due={due}, reason={reason}）",
                )
```

Leave `_social_tick` in place for now as an unused compatibility helper. Do not delete it in this task.

- [ ] **Step 4: Run targeted regression**

Run:

```bash
pytest tests/test_postprocess_regressions.py::test_life_tick_does_not_generate_every_turn_when_recent_event_exists -v
```

Expected: test passes.

- [ ] **Step 5: Run postprocess regression suite**

Run:

```bash
pytest tests/test_postprocess_regressions.py -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/core/postprocess.py tests/test_postprocess_regressions.py
git commit -m "feat: advance life simulation after turns"
```

---

### Task 11: Public Exports and Focused Full Verification

**Files:**
- Modify: `src/simulation/__init__.py`

- [ ] **Step 1: Export simulation classes**

Replace `src/simulation/__init__.py` with:

```python
"""Life simulation layer for Nan Gua."""

from .catchup_planner import CatchupPlanner
from .life_context_selector import LifeContextSelector
from .life_generator import LifeGenerator
from .life_receptivity import LifeReceptivity
from .life_scheduler import LifeScheduler
from .life_sharing_policy import LifeSharingPolicy
from .types import (
    CatchupDecision,
    LifeContextCandidate,
    LifeEventKind,
    ReceptivityResult,
    ShareLevel,
)

__all__ = [
    "CatchupDecision",
    "CatchupPlanner",
    "LifeContextCandidate",
    "LifeContextSelector",
    "LifeEventKind",
    "LifeGenerator",
    "LifeReceptivity",
    "LifeScheduler",
    "LifeSharingPolicy",
    "ReceptivityResult",
    "ShareLevel",
]
```

- [ ] **Step 2: Run all new tests**

Run:

```bash
pytest tests/test_life_receptivity.py tests/test_life_context_selector.py tests/test_catchup_planner.py tests/test_life_generator.py tests/test_life_scheduler.py tests/test_life_sharing_policy.py tests/test_life_context_integration.py tests/test_life_proactive_integration.py -v
```

Expected: all new tests pass.

- [ ] **Step 3: Run related existing tests**

Run:

```bash
pytest tests/test_storage_queries.py tests/test_trigger_manager.py tests/test_proactive_integration.py tests/test_postprocess_regressions.py tests/test_scheduler.py tests/test_social_integration.py -v
```

Expected: all listed tests pass.

- [ ] **Step 4: Commit exports**

```bash
git add src/simulation/__init__.py
git commit -m "chore: export life simulation modules"
```

---

### Task 12: Final Verification and v0.2 Readiness

**Files:**
- No code changes expected.

- [ ] **Step 1: Run full non-API suite**

Run:

```bash
pytest tests/ -v --ignore=tests/test_integration.py
```

Expected: all non-API tests pass. LLM-marked integration tests may skip when `DEEPSEEK_API_KEY` is not set.

- [ ] **Step 2: Inspect git diff**

Run:

```bash
git status --short
git log --oneline -12
```

Expected: working tree is clean after all task commits. Recent commits show the life simulation implementation tasks.

- [ ] **Step 3: Do not tag v0.2 yet**

Do not create `v0.2` until the user reviews the implementation behavior. The current public release remains `v0.1`; this feature branch becomes the candidate for `v0.2`.

---

## Self-Review Notes

Spec coverage:

- Life event layer: Tasks 4, 5, 6, 10.
- Existing social as a source: Task 6.
- Natural optional prompt injection: Tasks 3 and 7.
- Conservative proactive sharing and `mark_event_shared`: Tasks 8 and 9.
- Receptivity feedback loop: Tasks 2, 3, 8, 9.
- No guaranteed generation per user message: Tasks 4, 6, 10.
- No database schema rewrite: all tasks use existing `life_events` and `proactive_queue`.
- Future scheme three remains documented in the spec and is not implemented here.

Type consistency:

- `LifeScheduler.maybe_advance()` returns `list[dict]`.
- `LifeContextSelector.select()` returns `LifeContextCandidate | None`.
- `LifeSharingPolicy.select_event()` returns `LifeShareDecision | None`.
- Non-social `LifeEvent` rows use `event_type="life"` and `category` in `daily/creative/body_state/reflection`.
- Social rows keep the existing `event_type="social"` behavior.
