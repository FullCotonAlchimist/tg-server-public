# Telegram Gateway API Server

REST gateway for integrating Telegram API into backend infrastructures.

Abstraction layer that handles rate limiting constraints, request idempotency, and asynchronous event isolation.

---

## Overview

HTTP server that exposes the Telegram API via REST. Designed to be integrated into automation pipelines (n8n, Make, Airflow) where reliability and idempotency are critical.

Problems solved:

- Asyncio event isolation to prevent HTTP server blocking
- Automatic handling of `FloodWaitError` and Telegram rate limits
- Idempotency: network retries don't create duplicates
- Exponential retry with jitter on transient errors
- Response normalization (entities, media, metadata)
- Audio/video transcription for content indexing

### Technical Stack

- **Architecture**: Event loop isolation via dedicated thread
- **Resilience**: Exponential retry with adaptive backoff and jitter
- **Reliability**: SQLite idempotency cache with 2h TTL
- **Performance**: Thread-safe cache with temporal invalidation
- **Transcription**: Whisper small quantized int8 with language detection
- **Monitoring**: Multi-component health check (Telethon, Whisper, cache)
- **Deployment**: Docker with persistent volumes for session and cache

---

## Architecture

The system is built on a principle of strict separation of concerns:

```mermaid
graph TB
    HTTP[WSGI Server Waitress<br/>Single Worker / FIFO]
    Flask[Flask Routers<br/>Input Validation / Output Normalization]
    Cache[Idempotency Layer<br/>SQLite ACID / Mutex / TTL 7200s]
    Telegram[Isolated Telegram Client<br/>Dedicated Thread | Independent Event Loop | Rate Limiter]
    Pipeline[Processing Pipeline<br/>Data Extraction | Transcription | Formatting]
    
    HTTP --> Flask
    Flask --> Cache
    Cache --> Telegram
    Telegram --> Pipeline
    
    style HTTP fill:#e1f5ff
    style Flask fill:#fff4e1
    style Cache fill:#f0e1ff
    style Telegram fill:#e1ffe1
    style Pipeline fill:#ffe1e1
```

### Technical Decisions

**Single Worker Waitress**: A single thread processes HTTP requests sequentially. This guarantees FIFO order of operations to Telegram and eliminates race conditions on grouped message sending. Throughput is limited to ~6-12 messages/minute (4-20s delays between each operation to respect Telegram API limits). This throughput is inherent to Telegram quotas per account, not the server architecture.

**Event Loop Isolation**: The Telethon client runs in a separate thread with its own asyncio loop. HTTP requests are never blocked by Telegram I/O operations. Inter-thread communication via `asyncio.run_coroutine_threadsafe` with 1h timeout.

**Idempotency Cache**: SHA256 hash of `{"r": route, "d": body_json}` stored in SQLite with 2h TTL. Write operations are never executed twice, even on client-side retries. The hash includes the full request body to avoid collisions (not just the URL).

---

## Features

**Telegram Client**: Telethon implementation with automatic `FloodWaitError` handling. Rate limiting errors are handled internally with automatic retry. If the error persists after 3 attempts, it escalates to the HTTP client with a 500 code.

**Idempotency Layer**: Thread-safe ACID cache with temporal expiration (2h) and automatic cleanup. All POST requests are hashed and deduplicated.

**Message Extraction**: Paginated retrieval of channel histories with entity normalization (mentions, hashtags, custom emojis).

**Media Access**: Photo download and base64 encoding. Temporary files are deleted immediately after processing.

**Audio/Video Processing**: Automatic transcription with Whisper. Language detection from caption or automatic. Filtering of non-verbal content (music, noise).

**Scheduling**: Delayed message scheduling with support for grouped albums and forwards. Sequential order management and inter-send delays.

**Health Check**: `/health` endpoint that verifies Telethon status (connection + authorization), Whisper (model loaded), and cache (active entry count).

**HTML Parser**: Native converter from HTML syntax to Telegram entities. Correct UTF-16 offset handling for emojis.

---

## Project Structure

```
.
├── server.py               # Entry point, Waitress WSGI server
├── config.py               # Configuration via environment variables
├── telegram_client.py      # Telethon client, thread management, retry strategy
├── whisper_utils.py        # Transcription pipeline and language detection
├── cache.py                # Thread-safe SQLite idempotency layer
├── html_parser.py          # HTML to Telegram entities parser
├── requirements.txt        # Locked dependencies
├── Dockerfile              # Containerized image build
├── docker-compose.yml      # Deployment definition
├── .env.example            # Configuration template
└── routes/
    ├── health.py           # System monitoring endpoint
    ├── get_messages.py     # Message history retrieval
    ├── get_photos.py       # Media extraction
    ├── get_whisper.py      # Audio transcription processing
    ├── get_scheduled.py    # Scheduled messages consultation
    └── schedule_messages.py # Delayed operations scheduling
```

---

## Technical Modules

### telegram_client.py

Compliant client implementation:

- Isolated asyncio loop in a daemon thread
- Thread-safe inter-thread bridge for coroutine invocation
- Exponential retry strategy with jitter
- Native handling of `FloodWait` exceptions and automatic throughput adaptation
- Entity resolution cache for API call reduction
- Adaptive rate limiting by operation type

### cache.py

Idempotency layer:

- Unique SHA256 hash per (route, parameters) pair
- Write isolation via mutex
- Configurable TTL, 2 hours by default
- Automatic cleanup of expired entries
- Occupancy metrics exposed in health check

### whisper_utils.py

Transcription pipeline:

- Whisper small model with int8 quantization for CPU optimization
- Automatic language detection from caption metadata
- Non-verbal content filtering (music, noise)
- Language detection probability validation

### html_parser.py

Normalization component:

- Native Python parser without external dependencies
- Correct offset handling in UTF-16 encoding
- Support for bold, underline, and custom emoji formatting
- Direct conversion to native Telethon `MessageEntity` objects

---

## API Endpoints

### `GET /health`

> System status monitoring

```json
{
	"status": "ok",
	"telethon": "ok",
	"whisper": "ok",
	"cache_entries": 47
}
```

### `POST /get_messages`

> Channel history retrieval

```json
{
	"channel": "-100123456789",
	"last_message_id": 1872,
	"limit": 100,
	"offset_date": "2026-01-01T00:00:00+00:00"
}
```

### `POST /get_photos`

> Media extraction in standard base64 format

```json
{
	"canal_id": "-100123456789",
	"msg_ids": [1201, 1205, 1210]
}
```

### `POST /get_whisper_transcript`

> Audio/video transcription

```json
{
	"source_id": "-100123456789",
	"msg_ids": [1202, 1207],
	"language": "fr"
}
```

Downloads media, extracts audio with ffmpeg, transcribes with Whisper. The `language` parameter is optional: if absent, language is automatically detected from message caption or by Whisper.

### `POST /schedule_messages`

> Delayed message scheduling

Accepts an array of messages with different types: plain text, media with caption, forwards of existing messages, grouped albums. Each message must have a `scheduled_time` field in ISO 8601 format.

The idempotency cache ensures that the same batch will never be sent twice.

### `POST /get_scheduled_info`

> Scheduled operations queue consultation

```json
{
	"canal_id": "-100123456789"
}
```

Returns the number of scheduled messages and the date of the last planned message.

---

## Security

Deployment intended for private networks:

- No integrated authentication: implement via reverse proxy (Bearer token, mTLS, etc.)
- Binds to `127.0.0.1` by default in docker-compose
- Temporary files deleted immediately after processing
- No persistence of sensitive data beyond cache TTL (2h)
- Telethon session stored in isolated Docker volume

---

## Deployment

### Prerequisites

- Docker Engine 24+
- Valid Telegram developer account

### Procedure

```bash
# Configuration
cp .env.example .env
# Fill in API credentials in the .env file

# Session initialization
pip install -r requirements.txt
python -c "from telethon import TelegramClient; from config import API_ID, API_HASH, SESSION_NAME; c=TelegramClient(SESSION_NAME, API_ID, API_HASH); c.start()"

# Container startup
docker compose up -d --build
```

The service listens on `127.0.0.1:5000` by default in docker-compose.

---

## Environment Variables

- `TELEGRAM_API_ID`: Developer API identifier (required, obtain from https://my.telegram.org/apps)
- `TELEGRAM_API_HASH`: Developer API secret (required)
- `SESSION_NAME`: Telethon session file path (default: `session`)
- `PORT`: HTTP server listening port (default: `5000`)
- `TMP_DIR`: Temporary directory for downloaded media (default: `/tmp/tg_media`)

---

## Limitations

**Performance**: Throughput is limited to approximately 6-12 messages/minute (average ~5-10s per operation) by Telegram API quotas. Delays are variable: 4-7s (75%), 8-12s (20%), 13-20s (5%), with additional pauses every 10 messages. This throughput is a Telegram constraint, not the server: even with multiple workers, a single Telegram account cannot send faster.

**Transcription**: The Whisper small model may hallucinate on technical terms or proper nouns. Language detection probability is validated (0.65 threshold) but false positives remain possible on very short content.

**Persistence**: The idempotency cache and scheduled messages are volatile. A container restart loses the history of ongoing operations. For true production, the SQLite cache should be externalized to a persistent volume.

**Rate Limiting**: Delays between requests are calibrated conservatively (4-20s) to respect Telegram API quotas. On an account with established history and higher limits, these delays could be reduced.

---

## Logging

Logs are emitted in standard text format via Python's `logging` module (INFO level). Each critical operation is traced:

- Entity resolution and caching
- Duplicate request detection (cache hit)
- `FloodWaitError` handling with wait time
- Download or transcription errors

For integration with ELK/Loki, simply redirect container stdout/stderr or add a JSON handler to the logger.

---

## Use Cases

This server enables automated Telegram content operations within workflow automation platforms (n8n, Make, Airflow). Common applications:

**Message archiving**: Automated retrieval and storage of channel content with optional audio/video transcription for indexing.

**Scheduled publishing**: Batch message scheduling with media support. Idempotency ensures network retries don't create duplicates.

**Content aggregation**: Multi-source channel consolidation with content transformation and enrichment.

Additional applications include data extraction, sentiment analysis, trend detection, and compliance archiving.
