"""SQLite CRUD 操作。所有数据库访问通过此模块。"""

import json
from datetime import datetime
from typing import Optional

import aiosqlite

from .models import (
    User, Message, RelationshipEvent, Correction, ProactiveTask,
    LifeEvent, EvolutionEntry, RelationshipType, Direction, TriggerType,
    SocialCharacter, SocialArc, ArcStatus,
)


# ─── Users ──────────────────────────────────────────────────────

async def upsert_user(conn: aiosqlite.Connection, user: User) -> User:
    """创建或更新用户记录。"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    await conn.execute(
        """INSERT INTO users (user_id, platform, display_name, relationship_type,
           familiarity_score, branch_signal_streak, branch_type,
           interaction_count, deep_topics_count,
           user_initiated_count, late_night_count, corrections_count,
           first_interaction, last_interaction, topics_discussed,
           shared_jokes, notes, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(user_id) DO UPDATE SET
           display_name=excluded.display_name,
           interaction_count=excluded.interaction_count,
           deep_topics_count=excluded.deep_topics_count,
           user_initiated_count=excluded.user_initiated_count,
           late_night_count=excluded.late_night_count,
           corrections_count=excluded.corrections_count,
           last_interaction=excluded.last_interaction,
           familiarity_score=excluded.familiarity_score,
           branch_signal_streak=excluded.branch_signal_streak,
           branch_type=excluded.branch_type,
           relationship_type=excluded.relationship_type,
           topics_discussed=excluded.topics_discussed,
           shared_jokes=excluded.shared_jokes,
           notes=excluded.notes,
           updated_at=excluded.updated_at""",
        (
            user.user_id, user.platform, user.display_name, user.relationship_type.value,
            user.familiarity_score, user.branch_signal_streak, user.branch_type,
            user.interaction_count, user.deep_topics_count,
            user.user_initiated_count, user.late_night_count, user.corrections_count,
            user.first_interaction or now, now, user.topics_discussed,
            user.shared_jokes, user.notes, now,
        ),
    )
    await conn.commit()
    return user


async def get_user(conn: aiosqlite.Connection, user_id: str) -> Optional[User]:
    cursor = await conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = await cursor.fetchone()
    if row is None:
        return None
    return _row_to_user(row)


async def get_user_by_display_name(conn: aiosqlite.Connection, name: str) -> Optional[User]:
    cursor = await conn.execute("SELECT * FROM users WHERE display_name = ?", (name,))
    row = await cursor.fetchone()
    if row is None:
        return None
    return _row_to_user(row)


def _row_to_user(row) -> User:
    d = dict(row)
    return User(
        user_id=d["user_id"],
        platform=d.get("platform", "terminal"),
        display_name=d.get("display_name"),
        relationship_type=RelationshipType(d.get("relationship_type", "stranger")),
        familiarity_score=d.get("familiarity_score", 0.0),
        branch_signal_streak=d.get("branch_signal_streak", 0),
        branch_type=d.get("branch_type"),
        interaction_count=d.get("interaction_count", 0),
        deep_topics_count=d.get("deep_topics_count", 0),
        user_initiated_count=d.get("user_initiated_count", 0),
        late_night_count=d.get("late_night_count", 0),
        corrections_count=d.get("corrections_count", 0),
        first_interaction=d.get("first_interaction"),
        last_interaction=d.get("last_interaction"),
        topics_discussed=d.get("topics_discussed", "[]"),
        shared_jokes=d.get("shared_jokes", "[]"),
        notes=d.get("notes", ""),
        created_at=d.get("created_at"),
        updated_at=d.get("updated_at"),
    )


# ─── Messages ───────────────────────────────────────────────────

async def insert_message(conn: aiosqlite.Connection, msg: Message) -> Message:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor = await conn.execute(
        """INSERT INTO messages (user_id, direction, content, persona_state, deep_topic, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (msg.user_id, msg.direction.value, msg.content, msg.persona_state,
         int(msg.deep_topic), msg.created_at or now),
    )
    await conn.commit()
    msg.message_id = cursor.lastrowid
    return msg


async def get_recent_messages(
    conn: aiosqlite.Connection, user_id: str, limit: int = 20
) -> list[dict[str, str]]:
    cursor = await conn.execute(
        "SELECT direction, content FROM messages WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
        (user_id, limit),
    )
    rows = await cursor.fetchall()
    rows.reverse()
    return [{"role": "user" if r["direction"] == "incoming" else "assistant", "content": r["content"]} for r in rows]


# ─── Relationship Events ────────────────────────────────────────

async def log_relationship_event(
    conn: aiosqlite.Connection,
    user_id: str,
    event_type: str,
    old_state: dict,
    new_state: dict,
    trigger_message_id: Optional[int] = None,
):
    await conn.execute(
        """INSERT INTO relationship_events (user_id, event_type, old_state, new_state, trigger_message_id)
           VALUES (?, ?, ?, ?, ?)""",
        (user_id, event_type, json.dumps(old_state, ensure_ascii=False),
         json.dumps(new_state, ensure_ascii=False), trigger_message_id),
    )
    await conn.commit()


# ─── Corrections ────────────────────────────────────────────────

async def log_correction(
    conn: aiosqlite.Connection,
    user_id: Optional[str],
    source: str,
    target_file: str,
    description: str,
    applied: bool = False,
):
    await conn.execute(
        """INSERT INTO corrections (user_id, source, target_file, description, applied)
           VALUES (?, ?, ?, ?, ?)""",
        (user_id, source, target_file, description, int(applied)),
    )
    await conn.commit()


# ─── Proactive Queue ────────────────────────────────────────────

async def enqueue_proactive(
    conn: aiosqlite.Connection,
    user_id: str,
    trigger_type: TriggerType,
    message: str,
    scheduled_for: Optional[str] = None,
) -> int:
    cursor = await conn.execute(
        """INSERT INTO proactive_queue (user_id, trigger_type, proposed_message, scheduled_for)
           VALUES (?, ?, ?, ?)""",
        (user_id, trigger_type.value, message, scheduled_for),
    )
    await conn.commit()
    return cursor.lastrowid


async def get_pending_proactive(conn: aiosqlite.Connection, user_id: str) -> list[dict]:
    cursor = await conn.execute(
        "SELECT * FROM proactive_queue WHERE user_id = ? AND status = 'pending' ORDER BY created_at",
        (user_id,),
    )
    return [dict(r) for r in await cursor.fetchall()]


async def mark_proactive_sent(conn: aiosqlite.Connection, task_id: int):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    await conn.execute(
        "UPDATE proactive_queue SET status = 'sent', sent_at = ? WHERE task_id = ?",
        (now, task_id),
    )
    await conn.commit()


async def count_proactive_today(conn: aiosqlite.Connection, user_id: str) -> int:
    today = datetime.now().strftime("%Y-%m-%d")
    cursor = await conn.execute(
        "SELECT COUNT(*) as cnt FROM proactive_queue WHERE user_id = ? AND date(created_at) = ? AND status = 'sent'",
        (user_id, today),
    )
    row = await cursor.fetchone()
    return row["cnt"] if row else 0


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


# ─── Life Events ────────────────────────────────────────────────

async def insert_life_event(conn: aiosqlite.Connection, event: LifeEvent) -> LifeEvent:
    created_at = event.created_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor = await conn.execute(
        """INSERT INTO life_events (event_type, category, description, characters_involved, emotion, causality_chain_id, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (event.event_type, event.category, event.description,
         event.characters_involved, event.emotion, event.causality_chain_id,
         created_at),
    )
    await conn.commit()
    event.event_id = cursor.lastrowid
    event.created_at = created_at
    return event


async def get_recent_life_events(conn: aiosqlite.Connection, limit: int = 10) -> list[dict]:
    cursor = await conn.execute(
        "SELECT * FROM life_events ORDER BY created_at DESC LIMIT ?", (limit,)
    )
    return [dict(r) for r in await cursor.fetchall()]


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


# ─── Evolution Log ──────────────────────────────────────────────

async def insert_evolution_entry(conn: aiosqlite.Connection, entry: EvolutionEntry) -> EvolutionEntry:
    cursor = await conn.execute(
        """INSERT INTO evolution_log (cycle_date, behavior_patterns_checked, findings, growth_notes, written_back, shared_with_user)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (entry.cycle_date, entry.behavior_patterns_checked, entry.findings,
         entry.growth_notes, int(entry.written_back), int(entry.shared_with_user)),
    )
    await conn.commit()
    entry.entry_id = cursor.lastrowid
    return entry


async def get_last_evolution_entry(conn: aiosqlite.Connection) -> Optional[dict]:
    cursor = await conn.execute(
        "SELECT * FROM evolution_log ORDER BY created_at DESC LIMIT 1"
    )
    row = await cursor.fetchone()
    return dict(row) if row else None


# ─── Summaries ────────────────────────────────────────────────────

async def get_latest_summary(conn: aiosqlite.Connection, user_id: str) -> Optional[str]:
    cursor = await conn.execute(
        "SELECT summary_text FROM summaries WHERE user_id = ? ORDER BY created_at DESC LIMIT 1",
        (user_id,),
    )
    row = await cursor.fetchone()
    return row["summary_text"] if row else None


async def insert_summary(
    conn: aiosqlite.Connection,
    user_id: str,
    summary_text: str,
    range_start: int,
    range_end: int,
):
    await conn.execute(
        """INSERT INTO summaries (user_id, summary_text, message_range_start, message_range_end)
           VALUES (?, ?, ?, ?)""",
        (user_id, summary_text, range_start, range_end),
    )
    await conn.commit()


async def get_message_count_since_last_summary(conn: aiosqlite.Connection, user_id: str) -> int:
    cursor = await conn.execute(
        "SELECT MAX(message_range_end) as last_end FROM summaries WHERE user_id = ?",
        (user_id,),
    )
    row = await cursor.fetchone()
    last_end = row["last_end"] if row and row["last_end"] else 0
    cursor2 = await conn.execute(
        "SELECT COUNT(*) as cnt FROM messages WHERE user_id = ? AND message_id > ?",
        (user_id, last_end),
    )
    row2 = await cursor2.fetchone()
    return row2["cnt"] if row2 else 0


# ─── Open Loops ───────────────────────────────────────────────────

async def insert_open_loop(
    conn: aiosqlite.Connection,
    user_id: str,
    description: str,
    follow_up_window: str = "",
):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    await conn.execute(
        """INSERT INTO open_loops (user_id, description, detected_at, follow_up_window)
           VALUES (?, ?, ?, ?)""",
        (user_id, description, now, follow_up_window),
    )
    await conn.commit()


async def get_open_loops(conn: aiosqlite.Connection, user_id: str) -> list[dict]:
    cursor = await conn.execute(
        "SELECT * FROM open_loops WHERE user_id = ? AND status = 'open' ORDER BY created_at",
        (user_id,),
    )
    return [dict(r) for r in await cursor.fetchall()]


async def close_open_loop(conn: aiosqlite.Connection, loop_id: int):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    await conn.execute(
        "UPDATE open_loops SET status = 'closed', closed_at = ? WHERE loop_id = ?",
        (now, loop_id),
    )
    await conn.commit()


async def expire_stale_loops(conn: aiosqlite.Connection, user_id: str):
    await conn.execute(
        """UPDATE open_loops SET status = 'expired'
           WHERE user_id = ? AND status = 'open'
           AND date(created_at) < date('now', '-14 days')""",
        (user_id,),
    )
    await conn.commit()


# ─── Emotional Peaks ──────────────────────────────────────────────

async def insert_emotional_peak(
    conn: aiosqlite.Connection,
    user_id: str,
    message_id: int,
    weight: int,
    signals: list[str],
):
    await conn.execute(
        """INSERT INTO emotional_peaks (user_id, message_id, weight, signals)
           VALUES (?, ?, ?, ?)""",
        (user_id, message_id, weight, json.dumps(signals, ensure_ascii=False)),
    )
    await conn.commit()


# ─── Notes 追加 ───────────────────────────────────────────────────

async def append_user_note(conn: aiosqlite.Connection, user_id: str, note: str):
    """将一句话追加到 users.notes 字段。"""
    cursor = await conn.execute("SELECT notes FROM users WHERE user_id = ?", (user_id,))
    row = await cursor.fetchone()
    if row is None:
        return
    existing = row["notes"] or ""
    new_note = f"{existing}\n- {note}".strip() if existing else f"- {note}"
    await conn.execute(
        "UPDATE users SET notes = ?, updated_at = datetime('now', 'localtime') WHERE user_id = ?",
        (new_note, user_id),
    )
    await conn.commit()


# ─── Proactive Extras ──────────────────────────────────────────────

async def get_unshared_life_events(
    conn: aiosqlite.Connection, user_id: str, limit: int = 5
) -> list[dict]:
    """获取尚未分享给该用户的 life_events。"""
    cursor = await conn.execute(
        """SELECT * FROM life_events
           WHERE shared_with_users NOT LIKE ?
           ORDER BY created_at DESC LIMIT ?""",
        (f'%"{user_id}"%', limit),
    )
    return [dict(r) for r in await cursor.fetchall()]


async def mark_event_shared(
    conn: aiosqlite.Connection, event_id: int, user_id: str,
):
    """将 user_id 追加到 life_events.shared_with_users。"""
    cursor = await conn.execute(
        "SELECT shared_with_users FROM life_events WHERE event_id = ?",
        (event_id,),
    )
    row = await cursor.fetchone()
    if row is None:
        return
    shared = json.loads(row["shared_with_users"] or "[]")
    if user_id not in shared:
        shared.append(user_id)
    await conn.execute(
        "UPDATE life_events SET shared_with_users = ? WHERE event_id = ?",
        (json.dumps(shared, ensure_ascii=False), event_id),
    )
    await conn.commit()


async def has_milestone_been_sent(
    conn: aiosqlite.Connection, user_id: str, milestone_key: str,
) -> bool:
    """检查某个里程碑是否已经被发过主动消息。"""
    cursor = await conn.execute(
        """SELECT COUNT(*) as cnt FROM relationship_events
           WHERE user_id = ? AND event_type = ?""",
        (user_id, f"milestone_{milestone_key}"),
    )
    row = await cursor.fetchone()
    return (row["cnt"] if row else 0) > 0


# ─── Social Characters ────────────────────────────────────────────

async def upsert_character(conn: aiosqlite.Connection, c: SocialCharacter) -> SocialCharacter:
    await conn.execute(
        """INSERT INTO social_characters (character_id, name, source, traits, core_tension,
           relationship_to_nan_gua, current_arc_id, arc_cooldown_until, status, allowed_arc_types)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(character_id) DO UPDATE SET
           current_arc_id=excluded.current_arc_id,
           arc_cooldown_until=excluded.arc_cooldown_until,
           status=excluded.status""",
        (c.character_id, c.name, c.source, c.traits, c.core_tension,
         c.relationship_to_nan_gua, c.current_arc_id, c.arc_cooldown_until,
         c.status, c.allowed_arc_types),
    )
    await conn.commit()
    return c


async def get_all_characters(conn: aiosqlite.Connection) -> list[dict]:
    cursor = await conn.execute(
        "SELECT * FROM social_characters WHERE status = 'active' ORDER BY source, name"
    )
    return [dict(r) for r in await cursor.fetchall()]


async def get_character(conn: aiosqlite.Connection, character_id: str) -> Optional[dict]:
    cursor = await conn.execute(
        "SELECT * FROM social_characters WHERE character_id = ?", (character_id,)
    )
    row = await cursor.fetchone()
    return dict(row) if row else None


async def get_active_characters_count(conn: aiosqlite.Connection) -> int:
    cursor = await conn.execute(
        "SELECT COUNT(*) as cnt FROM social_characters WHERE status = 'active'"
    )
    row = await cursor.fetchone()
    return row["cnt"] if row else 0


# ─── Social Arcs ─────────────────────────────────────────────────

async def insert_arc(conn: aiosqlite.Connection, arc: SocialArc) -> SocialArc:
    await conn.execute(
        """INSERT INTO social_arcs (arc_id, character_id, arc_type, status, trigger_source,
           event_count, max_events)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (arc.arc_id, arc.character_id, arc.arc_type, arc.status.value,
         arc.trigger_source, arc.event_count, arc.max_events),
    )
    await conn.commit()
    return arc


async def get_active_arcs(conn: aiosqlite.Connection) -> list[dict]:
    cursor = await conn.execute(
        """SELECT * FROM social_arcs
           WHERE status IN ('setup', 'rising', 'climax', 'aftermath')
           ORDER BY started_at"""
    )
    return [dict(r) for r in await cursor.fetchall()]


async def get_arc(conn: aiosqlite.Connection, arc_id: str) -> Optional[dict]:
    cursor = await conn.execute(
        "SELECT * FROM social_arcs WHERE arc_id = ?", (arc_id,)
    )
    row = await cursor.fetchone()
    return dict(row) if row else None


async def update_arc_status(
    conn: aiosqlite.Connection, arc_id: str, status: str, ended: bool = False,
):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if ended:
        await conn.execute(
            "UPDATE social_arcs SET status = ?, ended_at = ? WHERE arc_id = ?",
            (status, now, arc_id),
        )
    else:
        await conn.execute(
            "UPDATE social_arcs SET status = ? WHERE arc_id = ?",
            (status, arc_id),
        )
    await conn.commit()


async def increment_arc_event_count(conn: aiosqlite.Connection, arc_id: str):
    await conn.execute(
        "UPDATE social_arcs SET event_count = event_count + 1 WHERE arc_id = ?",
        (arc_id,),
    )
    await conn.commit()
