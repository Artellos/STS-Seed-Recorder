import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "sts_recorder.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    with get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS seeds (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                seed_value TEXT NOT NULL,
                name       TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS nodes (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                seed_id   INTEGER NOT NULL REFERENCES seeds(id) ON DELETE CASCADE,
                act       INTEGER NOT NULL,
                floor     INTEGER NOT NULL,
                col       INTEGER NOT NULL,
                node_type TEXT NOT NULL,
                notes     TEXT DEFAULT '',
                on_path   INTEGER DEFAULT 0,
                UNIQUE(seed_id, act, floor, col)
            );

            CREATE TABLE IF NOT EXISTS connections (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                seed_id      INTEGER NOT NULL REFERENCES seeds(id) ON DELETE CASCADE,
                from_node_id INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
                to_node_id   INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
                UNIQUE(from_node_id, to_node_id)
            );
        """)
