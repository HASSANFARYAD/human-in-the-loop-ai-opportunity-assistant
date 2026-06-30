import aiosqlite
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from pathlib import Path

from mcp_shield.config import settings


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS shield_events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id        TEXT    NOT NULL UNIQUE,
    timestamp       TEXT    NOT NULL,
    session_id      TEXT,
    request_method  TEXT    NOT NULL,
    request_path    TEXT    NOT NULL,
    response_status INTEGER,
    latency_ms      INTEGER,
    llm_provider    TEXT,
    body_snapshot   TEXT,
    threat_type     TEXT,
    risk_score      REAL    DEFAULT 0.0,
    action_taken    TEXT    DEFAULT 'ALLOW',
    created_at      TEXT    DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS shield_alerts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id        TEXT    NOT NULL,
    alert_type      TEXT    NOT NULL,
    severity        TEXT    NOT NULL,
    detail          TEXT,
    created_at      TEXT    DEFAULT (datetime('now'))
);
"""


@asynccontextmanager
async def get_db() -> AsyncIterator[aiosqlite.Connection]:
    db_path = Path(settings.events_db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(str(db_path)) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA foreign_keys=ON")
        yield db


async def init_db() -> None:
    async with aiosqlite.connect(settings.events_db_path) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        for statement in _SCHEMA_SQL.split(";"):
            stmt = statement.strip()
            if stmt:
                await db.execute(stmt)
        await db.commit()


async def write_event(db: aiosqlite.Connection, event: dict) -> None:
    await db.execute(
        """
        INSERT INTO shield_events
            (event_id, timestamp, session_id, request_method, request_path,
             response_status, latency_ms, llm_provider, body_snapshot,
             threat_type, risk_score, action_taken)
        VALUES
            (:event_id, :timestamp, :session_id, :request_method, :request_path,
             :response_status, :latency_ms, :llm_provider, :body_snapshot,
             :threat_type, :risk_score, :action_taken)
        """,
        event,
    )
    await db.commit()


async def write_alert(db: aiosqlite.Connection, alert: dict) -> None:
    await db.execute(
        """
        INSERT INTO shield_alerts (event_id, alert_type, severity, detail)
        VALUES (:event_id, :alert_type, :severity, :detail)
        """,
        alert,
    )
    await db.commit()


async def get_recent_events(limit: int = 100) -> list[dict]:
    async with aiosqlite.connect(settings.events_db_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM shield_events ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_blocked_count_today() -> int:
    async with aiosqlite.connect(settings.events_db_path) as db:
        cursor = await db.execute(
            """
            SELECT COUNT(*) FROM shield_events
            WHERE action_taken = 'BLOCK'
              AND date(timestamp) = date('now')
            """,
        )
        row = await cursor.fetchone()
        return row[0] if row else 0


async def get_threat_summary() -> list[dict]:
    async with aiosqlite.connect(settings.events_db_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT threat_type, COUNT(*) AS count
            FROM shield_events
            WHERE threat_type IS NOT NULL
            GROUP BY threat_type
            ORDER BY count DESC
            """,
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_user_call_count(user_id: str) -> int:
    async with aiosqlite.connect(settings.events_db_path) as db:
        cursor = await db.execute(
            """
            SELECT COUNT(*) FROM shield_events
            WHERE session_id = ?
              AND date(timestamp) = date('now')
            """,
            (user_id,),
        )
        row = await cursor.fetchone()
        return row[0] if row else 0
