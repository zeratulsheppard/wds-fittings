import json
import sqlite3
from contextlib import contextmanager
from . import config

_SCHEMA = """
CREATE TABLE IF NOT EXISTS fittings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    ship_type_id INTEGER NOT NULL,
    ship_type_name TEXT NOT NULL,
    fit_json TEXT NOT NULL,
    owner_id INTEGER NOT NULL,
    owner_name TEXT NOT NULL,
    tags TEXT NOT NULL DEFAULT '[]',
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_fittings_owner ON fittings(owner_id);
CREATE INDEX IF NOT EXISTS idx_fittings_ship ON fittings(ship_type_id);
CREATE INDEX IF NOT EXISTS idx_fittings_updated ON fittings(updated_at DESC);
"""

_MIGRATIONS = [
    "ALTER TABLE fittings ADD COLUMN ship_group_id INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE fittings ADD COLUMN ship_group_name TEXT NOT NULL DEFAULT ''",
    "CREATE INDEX IF NOT EXISTS idx_fittings_group ON fittings(ship_group_id)",
    "ALTER TABLE fittings ADD COLUMN category TEXT NOT NULL DEFAULT ''",
    "CREATE INDEX IF NOT EXISTS idx_fittings_category ON fittings(category)",
]


def init_db() -> None:
    config.APP_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with connect() as conn:
        conn.executescript(_SCHEMA)
        for stmt in _MIGRATIONS:
            try:
                conn.execute(stmt)
            except sqlite3.OperationalError:
                pass  # column already exists / index already exists

    _backfill_ship_groups()


def _backfill_ship_groups() -> None:
    """Populate ship_group_id/name for any legacy row missing them."""
    from .sde import loader as sde
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, ship_type_id FROM fittings "
            "WHERE ship_group_id = 0 OR ship_group_name = ''"
        ).fetchall()
        for r in rows:
            info = sde.get_type(int(r["ship_type_id"]))
            if info is None:
                continue
            conn.execute(
                "UPDATE fittings SET ship_group_id = ?, ship_group_name = ? WHERE id = ?",
                (info.group_id, info.group_name, r["id"]),
            )


@contextmanager
def connect():
    conn = sqlite3.connect(config.APP_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def load_tags(raw: str) -> list:
    try:
        v = json.loads(raw or "[]")
        return [str(t).strip() for t in v if str(t).strip()]
    except (json.JSONDecodeError, TypeError):
        return []
