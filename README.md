# azura-ai

Telegram userbot that behaves like a real person: mood, memory, feelings, opinions, sleep, conflicts, choosing who to reply to and when to stay silent.

## Stack

- Python 3.12+, asyncio
- kurigram (maintained Pyrogram fork)
- SQLAlchemy 2.x + sqlite3 (WAL) + sqlite-vec + FTS5
- pydantic v2, Jinja2, loguru, openai SDK
- LLM via OnlySq API (OpenAI-compatible)

## Quick start

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .[dev]

copy .env.example .env
# put your ONLYSQ_API_KEY into .env

python -m azura.init_personality --interactive

python -m azura.run
```

## Layout

See `azura/` — modules `personality`, `db`, `memory`, `mind`, `llm`, `humanize`, `tools`, `telegram`, `utils`.

## TODO

- voice (TTS / STT)
- image generation (when the persona wants a "selfie")
- vision (full image analysis)
- multi-account
- memory export/import
