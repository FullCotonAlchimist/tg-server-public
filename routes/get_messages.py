from datetime import datetime, timezone, timedelta
from flask import Blueprint, request, jsonify
from telethon.tl.types import (
    MessageMediaPhoto,
    MessageMediaDocument,
    DocumentAttributeVideo,
    DocumentAttributeAudio,
)
from telegram_client import run, resolve_entity
from cache import req_hash, cache_get, cache_set
import logging

log = logging.getLogger(__name__)
get_messages_bp = Blueprint("get_messages", __name__)


@get_messages_bp.route("/get_messages", methods=["POST"])
def get_messages():
    data            = request.json or {}
    channel         = data.get("channel")
    last_message_id = int(data.get("last_message_id") or 0)
    days_ago        = int(data.get("days_ago") or 120)
    limit           = int(data.get("limit") or 1000)
    raw_date = data.get("offset_date")
    if raw_date and raw_date != "null":
        offset_date = datetime.fromisoformat(raw_date)
    else:
        offset_date = datetime.now(timezone.utc) - timedelta(days=days_ago)

    h = req_hash("/get_messages", data)
    cached = cache_get(h)
    if cached is not None:
        log.info("Duplicate /get_messages — returning cached result")
        return jsonify(cached)

    from telegram_client import _client

    async def fetch():
        entity   = await resolve_entity(channel)
        messages = []
        async for msg in _client.iter_messages(entity, min_id=last_message_id, offset_date=offset_date, reverse=True, limit=limit):
            messages.append(_serialize_message(msg))
        return messages

    result = run(fetch())
    cache_set(h, result)
    return jsonify(result)


def _serialize_message(msg):
    fwd      = msg.fwd_from
    fwd_from = None
    if fwd:
        fwd_from = {"from_name": getattr(fwd, "from_name", "") or ""}

    media = None
    if msg.media:
        if isinstance(msg.media, MessageMediaPhoto):
            media = {"_": "MessageMediaPhoto"}
        elif isinstance(msg.media, MessageMediaDocument):
            doc      = msg.media.document
            is_round = any(getattr(a, "round_message", False) for a in doc.attributes)
            is_voice = any(isinstance(a, DocumentAttributeAudio) and a.voice for a in doc.attributes)
            is_video = any(isinstance(a, DocumentAttributeVideo) for a in doc.attributes)
            media = {
                "_":        "MessageMediaDocument",
                "round":    is_round,
                "voice":    is_voice,
                "video":    is_video and not is_round and not is_voice,
                "document": {"id": doc.id},
            }

    return {
        "id":         msg.id,
        "message":    msg.message or "",
        "fwd_from":   fwd_from,
        "media":      media,
        "grouped_id": msg.grouped_id,
        "peer_id":    {"channel_id": msg.peer_id.channel_id if hasattr(msg.peer_id, "channel_id") else None},
        "date":       msg.date.isoformat() if msg.date else None,
        "entities":   [
            {
                "_": type(e).__name__,
                "offset": e.offset,
                "length": e.length,
                **({"document_id": "ID_" + str(e.document_id)} if hasattr(e, "document_id") else {})
            }
            for e in (msg.entities or [])
        ],
    }