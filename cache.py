import json
import time
import hashlib
import sqlite3
import threading
from pathlib import Path

_CACHE_TTL  = 7200  # 2 heures
_CACHE_DB   = Path(__file__).parent / "idempotency_cache.db"
_cache_lock = threading.Lock()


def _init_cache_db():
    con = sqlite3.connect(_CACHE_DB)
    con.execute("""
        CREATE TABLE IF NOT EXISTS cache (
            hash       TEXT PRIMARY KEY,
            result     TEXT NOT NULL,
            expires_at REAL NOT NULL
        )
    """)
    con.commit()
    con.close()

_init_cache_db()


def req_hash(route: str, data: dict) -> str:
    raw = json.dumps({"r": route, "d": data}, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


def cache_get(h: str):
    with _cache_lock:
        con = sqlite3.connect(_CACHE_DB)
        row = con.execute(
            "SELECT result FROM cache WHERE hash=? AND expires_at>?",
            (h, time.time())
        ).fetchone()
        con.close()
        return json.loads(row[0]) if row else None


def cache_set(h: str, result):
    with _cache_lock:
        con = sqlite3.connect(_CACHE_DB)
        con.execute(
            "INSERT OR REPLACE INTO cache (hash, result, expires_at) VALUES (?,?,?)",
            (h, json.dumps(result), time.time() + _CACHE_TTL)
        )
        con.execute("DELETE FROM cache WHERE expires_at <= ?", (time.time(),))
        con.commit()
        con.close()


def cache_active_count() -> int:
    with _cache_lock:
        con = sqlite3.connect(_CACHE_DB)
        count = con.execute(
            "SELECT COUNT(*) FROM cache WHERE expires_at>?", (time.time(),)
        ).fetchone()[0]
        con.close()
        return count