import base64
import logging
from pathlib import Path
from flask import Blueprint, request, jsonify
from telethon.tl.types import MessageMediaPhoto
from telegram_client import run, resolve_entity, safe_call, random_delay, long_pause_media
from cache import req_hash, cache_get, cache_set
from config import TMP_DIR

log = logging.getLogger(__name__)
get_photos_bp = Blueprint("get_photos", __name__)


@get_photos_bp.route("/get_photos", methods=["POST"])
def get_photos():
    data = request.json or {}
    h = req_hash("/get_photos", data)
    cached = cache_get(h)
    if cached is not None:
        log.info("Duplicate /get_photos — returning cached result")
        return jsonify(cached)

    canal_id = str(data.get("canal_id"))
    msg_ids  = [int(i) for i in data.get("msg_ids", [])]

    if not msg_ids:
        return jsonify({"photos": {}})

    from telegram_client import _client

    async def fetch():
        entity = await resolve_entity(int(canal_id))
        photos = {}

        for i, msg_id in enumerate(msg_ids):
            await random_delay()
            if i > 0 and i % 3 == 0:
                await long_pause_media()

            msg = await safe_call(_client.get_messages, entity, ids=msg_id)
            if not msg or not isinstance(msg.media, MessageMediaPhoto):
                continue

            photo_path = TMP_DIR / f"{canal_id}_{msg_id}.jpg"
            try:
                downloaded = await safe_call(_client.download_media, msg.media, file=str(photo_path))
                if downloaded:
                    with open(downloaded, "rb") as f:
                        photos[str(msg_id)] = base64.b64encode(f.read()).decode("utf-8")
            except Exception as e:
                log.error(f"Photo download error msg {msg_id}: {e}")
            finally:
                photo_path.unlink(missing_ok=True)

        return photos

    result = {"photos": run(fetch())}
    cache_set(h, result)
    return jsonify(result)