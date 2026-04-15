from flask import Blueprint, request, jsonify
from telegram_client import run, resolve_entity, safe_call

get_scheduled_bp = Blueprint("get_scheduled", __name__)


@get_scheduled_bp.route("/get_scheduled_info", methods=["POST"])
def get_scheduled_info():
    data     = request.json or {}
    canal_id = str(data.get("canal_id"))

    from telegram_client import _client

    async def fetch():
        entity         = await resolve_entity(int(canal_id))
        scheduled_msgs = await safe_call(_client.get_messages, entity, scheduled=True, limit=100)
        if not scheduled_msgs:
            return {"scheduled_count": 0, "last_scheduled_time": None}
        sorted_msgs = sorted([m for m in scheduled_msgs if m.date], key=lambda m: m.date)
        last_time   = sorted_msgs[-1].date.isoformat() if sorted_msgs else None
        return {"scheduled_count": len(scheduled_msgs), "last_scheduled_time": last_time}

    return jsonify(run(fetch()))