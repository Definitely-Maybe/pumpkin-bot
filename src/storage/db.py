"""SQLite 连接管理、schema 初始化、迁移。"""

import aiosqlite
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    platform TEXT NOT NULL DEFAULT 'terminal',
    display_name TEXT,
    relationship_type TEXT NOT NULL DEFAULT 'stranger',
    familiarity_score REAL NOT NULL DEFAULT 0.0,
    branch_signal_streak INTEGER NOT NULL DEFAULT 0,
    branch_type TEXT,
    interaction_count INTEGER NOT NULL DEFAULT 0,
    deep_topics_count INTEGER NOT NULL DEFAULT 0,
    user_initiated_count INTEGER NOT NULL DEFAULT 0,
    late_night_count INTEGER NOT NULL DEFAULT 0,
    corrections_count INTEGER NOT NULL DEFAULT 0,
    first_interaction TEXT,
    last_interaction TEXT,
    topics_discussed TEXT NOT NULL DEFAULT '[]',
    shared_jokes TEXT NOT NULL DEFAULT '[]',
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS messages (
    message_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    direction TEXT NOT NULL CHECK(direction IN ('incoming', 'outgoing')),
    content TEXT NOT NULL,
    persona_state TEXT NOT NULL DEFAULT '{}',
    deep_topic INTEGER NOT NULL DEFAULT 0,
    has_open_loop INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS relationship_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    old_state TEXT NOT NULL DEFAULT '{}',
    new_state TEXT NOT NULL DEFAULT '{}',
    trigger_message_id INTEGER,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (user_id) REFERENCES users(user_id),
    FOREIGN KEY (trigger_message_id) REFERENCES messages(message_id)
);

CREATE TABLE IF NOT EXISTS corrections (
    correction_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT,
    source TEXT NOT NULL DEFAULT 'user_said',
    target_file TEXT NOT NULL DEFAULT 'persona.md',
    description TEXT NOT NULL,
    applied INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS proactive_queue (
    task_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    trigger_type TEXT NOT NULL,
    proposed_message TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    scheduled_for TEXT,
    sent_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS life_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'daily',
    description TEXT NOT NULL,
    characters_involved TEXT NOT NULL DEFAULT '[]',
    emotion TEXT NOT NULL DEFAULT '',
    causality_chain_id TEXT,
    shared_with_users TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS evolution_log (
    entry_id INTEGER PRIMARY KEY AUTOINCREMENT,
    cycle_date TEXT NOT NULL,
    behavior_patterns_checked TEXT NOT NULL DEFAULT '[]',
    findings TEXT NOT NULL DEFAULT '',
    growth_notes TEXT NOT NULL DEFAULT '',
    written_back INTEGER NOT NULL DEFAULT 0,
    shared_with_user INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS summaries (
    summary_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    summary_text TEXT NOT NULL,
    message_range_start INTEGER NOT NULL DEFAULT 0,
    message_range_end INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS open_loops (
    loop_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    description TEXT NOT NULL,
    detected_at TEXT,
    follow_up_window TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','closed','expired')),
    closed_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS emotional_peaks (
    peak_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    message_id INTEGER NOT NULL,
    weight INTEGER NOT NULL DEFAULT 1 CHECK(weight >= 1 AND weight <= 3),
    signals TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (user_id) REFERENCES users(user_id),
    FOREIGN KEY (message_id) REFERENCES messages(message_id)
);

CREATE INDEX IF NOT EXISTS idx_messages_user ON messages(user_id);
CREATE INDEX IF NOT EXISTS idx_messages_created ON messages(created_at);
CREATE INDEX IF NOT EXISTS idx_relationship_user ON relationship_events(user_id);
CREATE INDEX IF NOT EXISTS idx_life_events_created ON life_events(created_at);
CREATE INDEX IF NOT EXISTS idx_life_events_chain ON life_events(causality_chain_id);
CREATE INDEX IF NOT EXISTS idx_summaries_user ON summaries(user_id);
CREATE INDEX IF NOT EXISTS idx_open_loops_user ON open_loops(user_id);
CREATE INDEX IF NOT EXISTS idx_open_loops_status ON open_loops(status);
CREATE INDEX IF NOT EXISTS idx_emotional_peaks_user ON emotional_peaks(user_id);

CREATE TABLE IF NOT EXISTS social_characters (
    character_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'fictional',
    traits TEXT NOT NULL DEFAULT '[]',
    core_tension TEXT NOT NULL DEFAULT '',
    relationship_to_nan_gua TEXT NOT NULL DEFAULT '',
    current_arc_id TEXT,
    arc_cooldown_until TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    allowed_arc_types TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS social_arcs (
    arc_id TEXT PRIMARY KEY,
    character_id TEXT NOT NULL,
    arc_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'setup',
    trigger_source TEXT NOT NULL DEFAULT '',
    started_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    ended_at TEXT,
    event_count INTEGER NOT NULL DEFAULT 0,
    max_events INTEGER NOT NULL DEFAULT 4,
    FOREIGN KEY (character_id) REFERENCES social_characters(character_id)
);

CREATE INDEX IF NOT EXISTS idx_social_arcs_character ON social_arcs(character_id);
CREATE INDEX IF NOT EXISTS idx_social_arcs_status ON social_arcs(status);
"""


async def _migrate(conn: aiosqlite.Connection) -> None:
    """Apply schema migrations that are idempotent (try/ignore)."""
    try:
        await conn.execute(
            "ALTER TABLE messages ADD COLUMN has_open_loop INTEGER NOT NULL DEFAULT 0"
        )
    except aiosqlite.OperationalError:
        pass  # column already exists

    try:
        await conn.execute(
            "ALTER TABLE users ADD COLUMN branch_signal_streak INTEGER NOT NULL DEFAULT 0"
        )
    except aiosqlite.OperationalError:
        pass

    try:
        await conn.execute(
            "ALTER TABLE users ADD COLUMN branch_type TEXT"
        )
    except aiosqlite.OperationalError:
        pass


async def init_db(db_path: str | Path) -> aiosqlite.Connection:
    """初始化数据库：创建表结构和索引。"""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = await aiosqlite.connect(str(db_path))
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA journal_mode=WAL")
    await conn.execute("PRAGMA foreign_keys=ON")
    await conn.executescript(SCHEMA)
    await _migrate(conn)
    await conn.commit()
    return conn


async def get_connection(db_path: str | Path) -> aiosqlite.Connection:
    """获取已有数据库的连接（不执行 schema）。"""
    db_path = Path(db_path)
    conn = await aiosqlite.connect(str(db_path))
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA journal_mode=WAL")
    await conn.execute("PRAGMA foreign_keys=ON")
    return conn
