# azura-ai

A Telegram **userbot** that behaves like a real human, not a chatbot. It has mood, separate per-chat short/long memory plus a global one, opinion- and feeling-memory, proximity tiers, conflict dynamics, sleep cycle with rare nightly wakeups, sticker/GIF collection with persona-fit tagging, and a tool-using LLM agent that decides what to do every turn.

Built on Python 3.11+, kurigram, SQLAlchemy 2.x + sqlite (WAL) + sqlite-vec + FTS5, pydantic v2, OpenAI SDK against the **OnlySq** OpenAI-compatible endpoint.

> Models: `claude-opus-4-6` for the speaking voice, `pplx-gemini-3.1-pro` for thinking (decide-to-reply, summaries, inner voice, persona generation, sticker tagging, nightly dreams), `text-embedding-3-small` for embeddings (1536d).

## What makes it not feel like a bot

- **Lives by a clock.** Sleeps per the persona's `wake`/`sleep` schedule, only rarely wakes at night (chance depends on impulsivity, fatigue, night_owl).
- **Chooses what to read.** Attention queue: `private → group → channel → muted_private → muted_group`. Within a tier, picked by unseen count, opinion, importance, mood and introversion.
- **Chooses whether to reply.** Probabilistic blend of traits, opinion, proximity, feelings, mood, urgency. "Read but didn't answer" is a real outcome. So is "ghost" and "react with a single emoji".
- **Has feelings that decay.** Time-weighted intensity per `(target, emotion)`.
- **Has opinions that aggregate.** Per-user score, per-chat score, and a chat-level score that blends chat opinion with member opinions.
- **Has a conflict engine.** Picks moves: deescalate / stand_ground / escalate / withdraw / passive_aggressive / side_with — by traits, derived conflict style, opponent aggression, topic importance.
- **Writes like a person.** Humanized delays (pre-read, typing chunks, after-send), occasional typos, sometimes self-corrects with `*word`, splits long answers into 2–4 short messages.
- **Has stickers and GIFs of its own.** Auto-collected from chats it sees, then LLM-tagged with mood/topic/persona-fit; used when they fit the moment.
- **Goes "away" for the internet.** Web search and fetch always wrap themselves in AFK with a believable reason, so you literally see the persona disappear and come back.
- **Never admits to being an AI.** Anti-detect filter strips bot-tells from outgoing text; system prompt is firm; reaction to accusation depends on the persona's humor style.
- **Has a journal.** Every significant state change writes a first-person line into the SQLite journal and a mirrored monthly `data/journal/YYYY-MM.md`.
- **Has nightly dreams.** While asleep, a dream pass softens grudges, strengthens fondnesses, picks fragments to keep as global memory, and writes a one-line dream entry.

## Project layout

See [`PROJECT_CONTEXT.md`](PROJECT_CONTEXT.md) for the full single-source-of-truth document (architecture, tables, traits, prompts, tools, decisions, progress).

Short tour:

```
azura/
├── config.py constants.py                   # settings, enums
├── utils/                                   # log, rng, timez, text
├── db/                                      # engine, models, fts, vec, schema, repo/*
├── personality/                             # pydantic schema, traits, loader+lock, generator
├── llm/                                     # AsyncOpenAI client, router, prompts, templates/
├── memory/                                  # short/long/daily/global/episodic + opinions/feelings/relationships + forgetting + consolidator + dreams + MemoryService
├── mind/                                    # clock, mood, presence, attention, intent, triggers, inner_voice, conflict, tails, life_events, household, social_graph, agent, scheduler
├── humanize/                                # delays, typing, typos, splitter, style_diversity, anti_detect, backpressure
├── tools/                                   # ToolContext, ToolRegistry, 9 families = 32 tools
├── telegram/                                # kurigram app, dispatcher, sender, reader, online, media_dl, stickers_collector, operator, patches
├── init_personality.py                      # CLI to generate persona JSON
└── run.py                                   # entry point
```

## Quick start (Windows / PowerShell)

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .[dev]

copy .env.example .env
# open .env and set ONLYSQ_API_KEY=...

python -m azura.init_personality --interactive
python -m azura.login           # one-time interactive Telegram login
python -m azura.run
```

`azura.login` does the phone/code/2FA dance once and writes `data/session.session`. After that `azura.run` starts silently. Re-running `azura.login` on an existing session just verifies it.

## Quick start (Linux)

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e .[dev]

cp .env.example .env
# edit .env

python -m azura.init_personality --interactive
python -m azura.login
python -m azura.run
```

For unattended deploy, see [`DEPLOY.md`](DEPLOY.md).

## Configuration

All keys live in `.env`. The important ones:

| key | default | meaning |
|---|---|---|
| `TG_API_ID` / `TG_API_HASH` | — | Telegram app credentials |
| `TG_SESSION_NAME` | `session` | filename under `data/` |
| `OPERATOR_ID` | `5624858175` | the only Telegram user allowed to issue control commands |
| `OPERATOR_SECRET` | `changeme` | prefix the operator must put on every command DM |
| `ONLYSQ_API_KEY` | empty | **you set this** |
| `MODEL_REPLY` | `claude-opus-4-6` | speaking model |
| `MODEL_THINK` | `pplx-gemini-3.1-pro` | thinking model |
| `MODEL_EMBED` | `text-embedding-3-small` | embeddings model |
| `EMBED_DIM` | `1536` | embedding column width for sqlite-vec |
| `HUMANIZE_MIN_REPLY_DELAY_S` | `2.5` | hard floor before any reply |
| `HUMANIZE_MAX_REPLY_DELAY_S` | `900` | hard ceiling |
| `HUMANIZE_TYPING_CHUNK_S` | `4.5` | typing keepalive cadence |
| `MEDIA_MAX_DOWNLOAD_MB` | `20` | size cap on direct-URL media downloads |
| `WEB_FETCH_TIMEOUT_S` | `15` | timeout for web tools |

## CLI

```
python -m azura.init_personality --interactive          # default; LLM fills in the rest
python -m azura.init_personality --auto                 # no questions, fully random
python -m azura.init_personality --critic 2             # 2 critic passes (1 by default)
python -m azura.init_personality --seed 12345           # explicit RNG seed
python -m azura.init_personality --overwrite            # skip confirmation
python -m azura.login                                   # one-time interactive TG login (writes session)
python -m azura.run                                     # boot the persona
```

## Operator channel

Only DMs from `OPERATOR_ID` whose body starts with `OPERATOR_SECRET` are honored. Commands:

| cmd | effect |
|---|---|
| `status` | mood + presence snapshot |
| `sleep` | force `asleep` |
| `wake` | force `online` |
| `pause` | force `offline` (no reads, no replies) |
| `resume` | back `online` |
| `journal [N]` | last N journal entries (default 10) |

## Persona immutability

`data/personality.json` is locked the moment it is generated. `data/personality.lock` stores two SHA256 digests (canonical dump + raw bytes). If either differs at boot, `run.py` aborts with a clear error. To regenerate: delete both files and re-run `init_personality`.

## Data on disk

```
data/
├── state.db                  # sqlite (WAL); see PROJECT_CONTEXT.md §6 for schema
├── session.session           # kurigram session
├── personality.json          # immutable persona
├── personality.lock          # SHA256 digests
├── journal/
│   ├── 2026-06.md            # monthly mirror
│   └── _current.md           # rolling "latest"
├── stickers/  gifs/  media_cache/
logs/
└── azura.log                 # loguru, 20 MB rotation, 10 files retained
```

The whole `data/` tree (except `personality.json` *itself*) and the `logs/` tree are gitignored.

## Troubleshooting

- **`ONLYSQ_API_KEY is empty`** — fill it in `.env`. The first LLM call will fail until you do.
- **`persona file modified after generation`** — you (or something) edited `data/personality.json`. Delete the JSON + lock and re-run `init_personality`.
- **Kurigram won't import** — make sure you installed `kurigram` (the pyrogram fork), not the upstream `pyrogram` package.
- **`sqlite-vec` missing extension** — `pip install -e .[dev]` again; this project unwraps aiosqlite to call `enable_load_extension`.
- **Sleep is not triggering on Windows** — check that `tzdata` is installed (it is in `requirements.txt` for win32).

## TODO

See [`TODO.md`](TODO.md) for the planned roadmap (voice, vision, multi-account, memory export, more).
