import subprocess
import logging
from pathlib import Path
from flask import Blueprint, request, jsonify
from telegram_client import run, resolve_entity, safe_call, random_delay, throttling_delay
from cache import req_hash, cache_get, cache_set
from config import TMP_DIR, TRANSCRIPTION_HINT
from whisper_utils import whisper_model, analyze_metadata_lang, is_non_speech_content

log = logging.getLogger(__name__)
get_whisper_bp = Blueprint("get_whisper", __name__)


@get_whisper_bp.route("/get_whisper_transcript", methods=["POST"])
def get_whisper_transcript():
    data = request.json or {}
    h = req_hash("/get_whisper_transcript", data)
    cached = cache_get(h)
    if cached is not None:
        log.info("Duplicate /get_whisper_transcript — returning cached result")
        return jsonify(cached)

    source_id = str(data.get("source_id"))
    msg_ids  = [int(i) for i in data.get("msg_ids", [])]
    lang     = data.get("language") or None

    if not msg_ids:
        return jsonify({"results": []})

    from telegram_client import _client

    async def fetch_and_transcribe():
        entity  = await resolve_entity(int(source_id))
        results = []

        for i, msg_id in enumerate(msg_ids):
            await random_delay()
            if i > 0 and i % 3 == 0:
                await throttling_delay()

            msg = await safe_call(_client.get_messages, entity, ids=msg_id)
            if not msg or not msg.media:
                continue

            whisper_lang = lang
            if not whisper_lang and msg.message and len(msg.message.strip()) > 15:
                caption_lang = analyze_metadata_lang(msg.message)
                if caption_lang:
                    whisper_lang = caption_lang
                    log.info(f"msg_id={msg_id} — langue détectée depuis caption : {whisper_lang}")

            media_path  = TMP_DIR / f"{source_id}_{msg_id}_media"
            downloaded  = await safe_call(_client.download_media, msg.media, file=str(media_path))
            if not downloaded:
                continue

            downloaded_path = Path(downloaded)
            audio_path      = TMP_DIR / f"{source_id}_{msg_id}.wav"
            try:
                subprocess.run([
                    "ffmpeg", "-y", "-i", str(downloaded_path),
                    "-ar", "16000", "-ac", "1", "-f", "wav", str(audio_path)
                ], check=True, capture_output=True)
                segments, info = whisper_model.transcribe(
                    str(audio_path),
                    language=whisper_lang or None,
                    beam_size=4,
                    initial_prompt=TRANSCRIPTION_HINT,
                    vad_filter=True
                )

                detected_lang = info.language
                lang_prob     = info.language_probability

                if not whisper_lang and detected_lang not in ('fr', 'en'):
                    results.append({"msg_id": msg_id, "transcription": "[aucune parole détectée]", "lang": "fr"})
                    continue

                if lang_prob < 0.65:
                    log.warning(f"msg_id={msg_id} — prob trop faible ({detected_lang}, {lang_prob:.2f})")
                    transcription = "[aucune parole détectée]"
                else:
                    text = " ".join(s.text.strip() for s in segments)
                    if len(text.strip()) < 15 or is_non_speech_content(text):
                        transcription = "[aucune parole détectée]"
                    else:
                        transcription = text

                results.append({"msg_id": msg_id, "transcription": transcription, "lang": detected_lang})

            except Exception as e:
                log.error(f"Transcription error msg {msg_id}: {e}")
                results.append({"msg_id": msg_id, "transcription": "[aucune parole détectée]", "lang": whisper_lang or "fr"})
            finally:
                downloaded_path.unlink(missing_ok=True)
                audio_path.unlink(missing_ok=True)

        return results

    result = {"results": run(fetch_and_transcribe())}
    cache_set(h, result)
    return jsonify(result)