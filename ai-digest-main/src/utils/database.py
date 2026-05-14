"""
utils/database.py — SQLite 去重 & 历史记录
"""
import sqlite3
import hashlib
from pathlib import Path
from datetime import datetime


DB_PATH = Path(__file__).parent.parent.parent / "data" / "digest.db"


def _get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """初始化数据库表"""
    with _get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS processed_items (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                url_hash    TEXT UNIQUE NOT NULL,
                url         TEXT,
                title       TEXT,
                source_name TEXT,
                platform    TEXT,
                processed_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS digest_runs (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                run_date    TEXT NOT NULL,
                items_count INTEGER DEFAULT 0,
                email_sent  INTEGER DEFAULT 0,
                created_at  TEXT DEFAULT (datetime('now'))
            );
        """)


def is_processed(url: str) -> bool:
    """检查 URL 是否已处理过"""
    url_hash = hashlib.sha256(url.encode()).hexdigest()
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT id FROM processed_items WHERE url_hash = ?", (url_hash,)
        ).fetchone()
        return row is not None


def mark_processed(url: str, title: str, source_name: str, platform: str):
    """标记 URL 为已处理"""
    url_hash = hashlib.sha256(url.encode()).hexdigest()
    with _get_conn() as conn:
        conn.execute(
            """INSERT OR IGNORE INTO processed_items
               (url_hash, url, title, source_name, platform)
               VALUES (?, ?, ?, ?, ?)""",
            (url_hash, url, title, source_name, platform),
        )


def record_run(items_count: int, email_sent: bool):
    """记录本次运行"""
    with _get_conn() as conn:
        conn.execute(
            "INSERT INTO digest_runs (run_date, items_count, email_sent) VALUES (?, ?, ?)",
            (datetime.now().strftime("%Y-%m-%d"), items_count, int(email_sent)),
        )
