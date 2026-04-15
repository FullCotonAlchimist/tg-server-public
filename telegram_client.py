import asyncio
import random
import logging
import threading
from telethon import TelegramClient
from telethon.errors import FloodWaitError
from telethon.tl.functions.channels import GetChannelsRequest
from telethon.tl.types import InputChannel
from config import API_ID, API_HASH, SESSION_NAME

log = logging.getLogger(__name__)

_loop   = asyncio.new_event_loop()
_client = TelegramClient(
    SESSION_NAME, API_ID, API_HASH,
    device_model="iPhone 14 Pro",
    system_version="16.6",
    app_version="9.6.3",
    lang_code="fr",
    system_lang_code="fr-FR",
)


def _start_loop():
    asyncio.set_event_loop(_loop)
    _loop.run_forever()

threading.Thread(target=_start_loop, daemon=True).start()


def run(coro):
    """Exécute une coroutine dans la loop Telethon depuis n'importe quel thread."""
    return asyncio.run_coroutine_threadsafe(coro, _loop).result(timeout=3600)


# Connexion initiale
run(_client.connect())
log.info(f"Telethon connecté : {run(_client.is_user_authorized())}")


_entity_cache: dict = {}


async def resolve_entity(identifier):
    key = str(identifier)
    if key in _entity_cache:
        return _entity_cache[key]

    id_str = str(identifier)
    if id_str.startswith('-100'):
        channel_id = int(id_str.replace('-100', ''))
        result = await _client(GetChannelsRequest([InputChannel(channel_id, 0)]))
        if result.chats:
            entity = result.chats[0]
            _entity_cache[key] = entity
            log.info(f"Entité {identifier} résolue via GetChannelsRequest et mise en cache")
            return entity
        raise ValueError(f"Channel introuvable : {identifier}")

    try:
        entity = await _client.get_entity(identifier)
        _entity_cache[key] = entity
        return entity
    except ValueError:
        raise ValueError(f"Entité introuvable : {identifier}")


async def safe_call(coro_fn, *args, max_retries=3, **kwargs):
    for attempt in range(max_retries):
        try:
            return await coro_fn(*args, **kwargs)
        except FloodWaitError as e:
            wait = e.seconds + random.uniform(5, 15)
            log.warning(f"FloodWaitError: {e.seconds}s → attente {wait:.1f}s (tentative {attempt+1}/{max_retries})")
            if attempt == max_retries - 1:
                log.error(f"FloodWaitError persistant après {max_retries} tentatives — abandon")
                raise
            await asyncio.sleep(wait)
        except Exception as e:
            if attempt == max_retries - 1:
                log.error(f"Échec après {max_retries} tentatives : {e}")
                raise
            wait = (2 ** attempt) * random.uniform(3, 7)
            log.warning(f"Erreur transitoire ({e}), retry dans {wait:.1f}s (tentative {attempt+1}/{max_retries})")
            await asyncio.sleep(wait)
    return None


async def random_delay():
    delay = random.choices(
        [random.uniform(4, 7), random.uniform(8, 12), random.uniform(13, 20)],
        weights=[75, 20, 5]
    )[0]
    await asyncio.sleep(delay)


async def throttling_delay():
    await asyncio.sleep(random.uniform(6, 12))


async def long_pause_media():
    await asyncio.sleep(random.uniform(10, 20))


async def long_pause_schedule():
    await asyncio.sleep(random.uniform(8, 15))


def to_channel_id(channel_id) -> str:
    s = str(channel_id)
    return s if s.startswith('-100') else f"-100{s}"