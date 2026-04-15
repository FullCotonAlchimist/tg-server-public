import logging
from datetime import datetime
from flask import Blueprint, request, jsonify
from telegram_client import run, resolve_entity, safe_call, random_delay, long_pause_schedule, to_channel_id
from cache import req_hash, cache_get, cache_set
from html_parser import parse_telegram_html

log = logging.getLogger(__name__)
schedule_messages_bp = Blueprint("schedule_messages", __name__)


@schedule_messages_bp.route("/schedule_messages", methods=["POST"])
def schedule_messages():
    data = request.json or {}
    h = req_hash("/schedule_messages", data)
    cached = cache_get(h)
    if cached is not None:
        log.info("Duplicate /schedule_messages — returning cached result (no double scheduling)")
        return jsonify(cached)

    dest_channel   = data.get("dest_channel")
    source_channel = data.get("source_channel")
    messages       = data.get("messages", [])

    from telegram_client import _client

    async def send_all():
        dest_entity   = await resolve_entity(dest_channel)
        source_entity = await resolve_entity(source_channel)

        batched = []
        i = 0
        while i < len(messages):
            msg = messages[i]
            if msg.get("type") == "forwarded_message" and msg.get("grouped_id"):
                gid   = msg["grouped_id"]
                group = [msg]
                j     = i + 1
                while j < len(messages) and \
                        messages[j].get("type") == "forwarded_message" and \
                        messages[j].get("grouped_id") == gid:
                    group.append(messages[j])
                    j += 1
                batched.append(("album_forward", group))
                i = j
            else:
                batched.append(("single", msg))
                i += 1

        errors = 0
        sent   = 0

        for idx, (batch_type, batch) in enumerate(batched):
            await random_delay()
            if idx > 0 and idx % 10 == 0:
                await long_pause_schedule()

            if batch_type == "album_forward":
                msg       = batch[0]
                source_ref = to_channel_id(msg.get("source_channel") or source_channel)
                if str(source_ref) == str(source_channel):
                    reference_peer = source_entity
                else:
                    reference_peer = await resolve_entity(source_ref)
                ids         = [int(m["source_msg_id"]) for m in batch]
                schedule_dt = datetime.fromisoformat(msg["scheduled_time"].replace("Z", "+00:00"))
                src_msgs    = await safe_call(_client.get_messages, reference_peer, ids=ids)
                if src_msgs:
                    src_msgs = [m for m in src_msgs if m is not None]
                if src_msgs:
                    await safe_call(_client.forward_messages, dest_entity, src_msgs, schedule=schedule_dt)
                    sent += len(src_msgs)
                else:
                    log.warning(f"Album forward: messages {ids} not found in source {source_ref}")
                    errors += len(ids)
                continue

            msg            = batch
            msg_type       = msg.get("type")
            content        = msg.get("message") or msg.get("content", "")
            media_id       = msg.get("media_id")
            if media_id is not None:
                try:
                    media_id = int(media_id)
                except (ValueError, TypeError):
                    log.warning(f"media_id invalide '{media_id}' ignoré (hallucination) pour msg type={msg_type}")
                    media_id = None
            scheduled_time = msg.get("scheduled_time")
            if not scheduled_time:
                log.error(f"scheduled_time manquant pour msg {msg}")
                errors += 1
                continue
            try:
                schedule_dt = datetime.fromisoformat(scheduled_time.replace("Z", "+00:00"))
            except ValueError as e:
                log.error(f"scheduled_time invalide '{scheduled_time}' pour msg {msg}: {e}")
                errors += 1
                continue

            if msg_type in ("text_with_media", "text_message", "summary_text", "link_message", "header_text"):
                log.info(f"[parse] raw content={content!r}")
                _plain, _ents = parse_telegram_html(content)
                log.info(f"[parse] plain={_plain!r}")
                log.info(f"[parse] entities={_ents}")
                if media_id:
                    media_src    = msg.get("media_source_channel")
                    media_entity = await resolve_entity(to_channel_id(media_src)) if media_src else source_entity
                    src_msg      = await safe_call(_client.get_messages, media_entity, ids=int(media_id))
                    file         = src_msg.media if src_msg and src_msg.media else None
                    await safe_call(_client.send_message, dest_entity, _plain, file=file, schedule=schedule_dt, formatting_entities=_ents or None)
                else:
                    await safe_call(_client.send_message, dest_entity, _plain, schedule=schedule_dt, formatting_entities=_ents or None)
                sent += 1

            elif msg_type == "media_message":
                if not media_id:
                    log.warning(f"Media message missing media_id, skipped: {msg}")
                    errors += 1
                    continue
                media_src    = msg.get("media_source_channel")
                media_entity = await resolve_entity(to_channel_id(media_src)) if media_src else source_entity
                src_msg      = await safe_call(_client.get_messages, media_entity, ids=int(media_id))
                if src_msg and src_msg.media:
                    if content:
                        _plain, _ents = parse_telegram_html(content)
                        await safe_call(_client.send_message, dest_entity, _plain, file=src_msg.media, schedule=schedule_dt, formatting_entities=_ents or None)
                    else:
                        await safe_call(_client.send_message, dest_entity, None, file=src_msg.media, schedule=schedule_dt)
                    sent += 1
                else:
                    log.warning(f"Media message: media {media_id} not found in {media_src or source_channel}")
                    errors += 1

            elif msg_type == "stored_media":
                if not media_id:
                    log.warning(f"Stored media missing media_id, skipped: {msg}")
                    errors += 1
                    continue
                storage_source = to_channel_id(msg.get("media_storage_channel") or source_channel)
                storage_entity = await resolve_entity(storage_source)
                src_msg = await safe_call(_client.get_messages, storage_entity, ids=int(media_id))
                if src_msg and src_msg.media:
                    await safe_call(_client.send_message, dest_entity, src_msg.message or "", file=src_msg.media, schedule=schedule_dt)
                    sent += 1
                else:
                    log.warning(f"Stored media: message {media_id} not found in storage channel {storage_source}")
                    errors += 1

            elif msg_type == "forwarded_message":
                source_msg_id = msg.get("source_msg_id")
                if not source_msg_id:
                    log.warning(f"Forwarded message missing source_msg_id, skipped: {msg}")
                    errors += 1
                    continue
                source_ref = to_channel_id(msg.get("source_channel") or source_channel)
                if str(source_ref) == str(source_channel):
                    reference_peer = source_entity
                else:
                    reference_peer = await resolve_entity(source_ref)
                src_msg = await safe_call(_client.get_messages, reference_peer, ids=int(source_msg_id))
                if src_msg:
                    await safe_call(_client.forward_messages, dest_entity, src_msg, schedule=schedule_dt)
                    sent += 1
                else:
                    log.warning(f"Forwarded message {source_msg_id} not found in source {source_ref}")
                    errors += 1

            else:
                log.warning(f"Unknown message type ignored: {msg_type}")
                errors += 1

        return {"ok": True, "errors": errors, "sent": sent}

    result = run(send_all())
    cache_set(h, result)
    return jsonify(result)