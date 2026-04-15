import asyncio
import sqlite3
import time
from flask import Blueprint, jsonify
from telegram_client import _client, _loop
from whisper_utils import whisper_model
from cache import _cache_lock, _CACHE_DB

health_bp = Blueprint("health", __name__)


@health_bp.route("/health", methods=["GET"])
def health():
    checks = {}

    try:
        authorized = asyncio.run_coroutine_threadsafe(_client.is_user_authorized(), _loop).result(timeout=5)
        checks["telethon"] = "ok" if authorized else "unauthorized"
    except Exception as e:
        checks["telethon"] = f"error: {e}"

    checks["whisper"] = "ok" if whisper_model is not None else "not loaded"

    with _cache_lock:
        con = sqlite3.connect(_CACHE_DB)
        active = con.execute(
            "SELECT COUNT(*) FROM cache WHERE expires_at>?", (time.time(),)
        ).fetchone()[0]
        con.close()
    checks["cache_entries"] = active

    ok = all(v == "ok" or isinstance(v, int) for v in checks.values())
    return jsonify({"status": "ok" if ok else "degraded", **checks}), 200 if ok else 500