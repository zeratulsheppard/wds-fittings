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


def init_db() -> None:
    config.APP_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with connect() as conn:
        conn.executescript(_SCHEMA)


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
