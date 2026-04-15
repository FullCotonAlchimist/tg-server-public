import os
import logging
from pathlib import Path

API_ID       = int(os.environ["TELEGRAM_API_ID"])
API_HASH     = os.environ["TELEGRAM_API_HASH"]
SESSION_NAME = os.environ.get("SESSION_NAME", "session")
LISTEN_PORT  = int(os.environ.get("PORT", 5000))
TMP_DIR      = Path(os.environ.get("TMP_DIR", "/tmp/tg_media"))

if TMP_DIR.exists():
    for _f in TMP_DIR.glob("*"):
        try:
            _f.unlink()
        except Exception:
            pass
TMP_DIR.mkdir(parents=True, exist_ok=True)

TRANSCRIPTION_HINT = "" # [REDACTED]

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)