# azura-ai — Project Context

> Single source of truth for the project. If you start a fresh session, paste this file to bring the assistant fully up to speed.
> Last sync: 2026-06-02.

---

## 1. Goal

A Telegram **userbot** behaving like a real human, not a bot. It must:

- Choose which chats to read and when to stay silent.
- Step away (AFK / asleep / busy) with believable, self-justified reasons logged to memory.
- Hold separate **short** and **long** memories per chat, plus a **global** memory, plus **opinion-memory** and **feeling-memory**.
- Have a mood driven by randomizers, traits and time-of-day.
- Write first; analyze chats; react to text, files, photos, stickers, GIFs.
- Collect stickers/GIFs it sees in chats, tag them by mood/topic, and reuse the ones that fit its character + the moment.
- Use the internet but visibly "go offline" while it does.
- Speak only its declared native languages; for others, "pretend to use a translator".
- Live on a real day cycle: sleep, occasional brief wakeups; never online 24/7.
- Maintain proximity tiers (stranger / acquaintance / friend / close) and apply them to tone and reply thresholds.
- Have conflict dynamics, grudges, forgiveness.
- Have an **operator** channel (Telegram ID `5624858175`) for control.
- Be 100% an agent with many tools, picking the relevant ones per situation.
- Run on LLMs from the OnlySq API (`claude-opus-4-6` to talk, `pplx-gemini-3.1-pro` to think).

`ONLYSQ_API_KEY` is empty in `.env` — the user sets it.

---

## 2. Stack

- Python **3.11+** (target 3.12, but install supports 3.11).
- **kurigram** (maintained Pyrogram fork), `tgcrypto-pyrofork`.
- **SQLAlchemy 2.x async** + `aiosqlite` + **sqlite3 WAL** + **sqlite-vec** + **FTS5**.
- **pydantic v2**, **pydantic-settings**.
- **httpx**, **openai** SDK (AsyncOpenAI against OnlySq OpenAI-compatible endpoint).
- **Jinja2**, **loguru**, **orjson**, **rich**, **prompt-toolkit**, **numpy**, **tzdata** (win32).

### OnlySq API

- Base URL: `https://api.onlysq.ru/ai/openai` (no `/v1`).
- OpenAI-compatible. Use `AsyncOpenAI(base_url=..., api_key=...)`.
- Models in use:
  - `MODEL_REPLY=claude-opus-4-6` — speaking voice (final replies).
  - `MODEL_THINK=pplx-gemini-3.1-pro` — thinking (decide-to-reply, summaries, inner voice, persona generation, critic, sticker tagging, dreams).
  - `MODEL_EMBED=text-embedding-3-small` (1536 dims) — embeddings for sqlite-vec.

---

## 3. Code style rules (binding)

- **No comments inside code.** All explanations go into `"""docstrings"""`.
- Short variable names (`r`, `m`, `s`, `ctx`, …) but readable.
- Strict modularity; each file owns one responsibility.
- English in code, identifiers, docstrings.
- Russian only in user-facing strings the persona may produce.
- Persona is **immutable** after generation: SHA256 lock on canonical dump + raw file bytes.

---

## 4. Repository layout

```
azura-ai/
├── PROJECT_CONTEXT.md            # this file
├── README.md
├── pyproject.toml
├── requirements.txt
├── .env / .env.example / .gitignore
├── azura/
│   ├── __init__.py
│   ├── config.py                 # pydantic-settings, Settings + get_settings()
│   ├── constants.py              # ChatKind, Presence, MemoryKind, Proximity, PROXIMITY_THRESHOLDS, ATTENTION_ORDER, PERSONALITY_TRAITS (28)
│   ├── init_personality.py       # CLI: --interactive (default), --auto, --critic N, --seed, --overwrite
│   ├── run.py                    # entry point (planned)
│   │
│   ├── utils/
│   │   ├── log.py                # loguru setup_logging + get_logger
│   │   ├── rng.py                # Rng (seeded), stable_hash
│   │   ├── timez.py              # now_in, in_window, parse_hhmm, seconds_until
│   │   └── text.py               # normalize, words, ngrams, find_mentions, contains_name
│   │
│   ├── db/
│   │   ├── engine.py             # async engine, WAL + sqlite-vec via aiosqlite unwrap
│   │   ├── models.py             # 14 ORM tables (see §6)
│   │   ├── fts.py                # FTS5 virtual tables + fts_quote() escaping
│   │   ├── vec.py                # vec0 virtual tables + knn search
│   │   ├── schema.py             # init_schema(embed_dim)
│   │   └── repo/
│   │       ├── __init__.py       # Repos facade (15 repos)
│   │       ├── chats.py users.py messages.py memory.py episodes.py
│   │       ├── opinions.py feelings.py relationships.py
│   │       ├── mood.py presence.py stickers.py gifs.py
│   │       ├── attention.py journal.py kv.py
│   │
│   ├── personality/
│   │   ├── schema.py             # pydantic v2 Persona, Identity, SpeechStyle (alias 'register'), DailyRhythm,
│   │   │                         # SocialBehavior, Household, SocialCircle, LifeEvent, CurrentLifeArc, Boundaries
│   │   ├── traits.py             # normalize_traits, derive_attachment/humor/conflict
│   │   ├── loader.py             # save_persona / load_persona / verify_lock / ensure_immutable (dual hash)
│   │   └── generator.py          # draft -> critic-loop -> normalize -> validate
│   │
│   ├── llm/
│   │   ├── client.py             # AsyncOpenAI, retries (RateLimit/APIConnection/5xx), chat / chat_text / chat_json / embed
│   │   ├── router.py             # reply_*, think_*, embed_texts
│   │   ├── prompts.py            # Jinja2 loader, render('name.j2', **ctx)
│   │   └── templates/
│   │       ├── persona_outline.j2 persona_user.j2 persona_critic.j2
│   │       ├── system_human.j2   # main persona system prompt (anti-AI clause)
│   │       └── inner_voice.j2
│   │
│   ├── memory/
│   │   ├── service.py            # MemoryService facade: short/long/daily/global_/episodic/opinions/feelings/relationships/forgetting/embeds
│   │   ├── short_term.py long_term.py daily.py global_mem.py episodic.py
│   │   ├── opinions.py feelings.py relationships.py
│   │   ├── forgetting.py         # half-life per tier, eviction
│   │   └── embeds.py             # in-memory embed cache
│   │
│   ├── mind/
│   │   ├── clock.py              # snapshot, _phase, is_sleep_window, is_work_window
│   │   ├── mood.py               # MoodView, baseline_for, MoodEngine: drift/nudge/sleep_reset/journal_if_significant
│   │   ├── presence.py           # PresenceEngine (asleep/offline/afk/online/busy), random wakeups
│   │   ├── attention.py          # ranked queue: private→group→channel→muted_private→muted_group
│   │   ├── intent.py             # IntentEngine: reply/read_only/react/later/ignore; decide_first_message
│   │   ├── triggers.py           # name/@/keyword/boundary; urgency()
│   │   ├── inner_voice.py        # private think-pass → feeling, want_to_reply, tone, opinion_delta
│   │   ├── conflict.py           # ConflictEngine, ConflictDecision
│   │   ├── tails.py              # TailQueue: 'oh, also...' follow-ups
│   │   ├── life_events.py        # random coffee/shower/walk events → AFK
│   │   ├── household_context.py  # prompt-injectable household lines
│   │   ├── social_graph.py       # neighbors, picks_side
│   │   ├── agent.py              # Agent: tool-loop on opus, ToolSpec
│   │   └── scheduler.py          # MindScheduler: heartbeat/life_events/tails/forgetting asyncio loops
│   │
│   ├── humanize/
│   │   ├── delays.py             # reply_delay(): pre_read/pre_type/type_burst/after_send + clamps
│   │   ├── typing.py             # type_with_ticks (keepalive cycles)
│   │   ├── typos.py              # 4 typo ops, ru+en neighbours, follow-up corrections
│   │   ├── splitter.py           # split_reply + soft fallback (commas/conjunctions)
│   │   ├── style_diversity.py    # n-gram overlap window
│   │   ├── anti_detect.py        # has_chatbot_smell, sanitize, ru+en bot tells
│   │   └── backpressure.py       # global min-gap + per-chat per-minute cap
│   │
│   ├── tools/
│   │   ├── context.py            # ToolContext: persona+memory+mood+presence+conflict+tails + bound senders
│   │   ├── registry.py           # ToolRegistry, make_spec
│   │   ├── builder.py            # build_registry(ctx), default_tool_subset (no operator)
│   │   ├── memory_tools.py       # recall_user/recall_chat/search_memory/remember_fact/remember_episode/update_opinion/update_feeling/note_relationship
│   │   ├── self_tools.py         # go_afk/come_back/set_presence/nudge_mood/journal
│   │   ├── chat_tools.py         # mute_chat/unmute_chat/set_chat_importance
│   │   ├── send_tools.py         # send_messages/send_sticker/send_gif/send_media/schedule_tail
│   │   ├── sticker_tools.py      # pick_sticker/learn_sticker
│   │   ├── gif_tools.py          # pick_gif/learn_gif
│   │   ├── media_tools.py        # note_media (vision later)
│   │   ├── web_tools.py          # web_search/web_fetch (wrapped in AFK)
│   │   └── operator_tools.py     # op_status/op_force_sleep/op_force_wake/op_journal
│   │
│   └── telegram/
│       ├── app.py                # make_client(settings) → kurigram Client (userbot)
│       ├── patches.py            # apply() patches kurigram (get_peer_type)
│       ├── online.py             # push_status(client, presence_view) via account.UpdateStatus RPC
│       ├── senders.py            # Sender: pre_read → typing → typos → multi-message → backpressure → anti-detect
│       ├── readers.py            # Reader.cycle(mood): walks attention.queue() reading chats in tier order
│       ├── media_dl.py           # download(url) → media_cache (size cap, scheme allow-list, SSRF private-IP guard)
│       ├── stickers_collector.py # StickersCollector: persist file_id, LLM-tag mood/desc/fits_persona
│       ├── operator.py           # handle(msg, ctx, settings): TG id + secret prefix; commands: status/sleep/wake/journal/pause/resume
│       ├── reply_formatter.py    # build_user_prompt(memory, chat, user, trigger) — JSON situation for agent
│       └── handlers.py           # Dispatcher: per-chat lock + fresh AsyncSession; record→trigger→intent→agent→sender
│
│
├── data/                         # gitignored runtime
│   ├── state.db                  # sqlite (WAL)
│   ├── session.session           # kurigram session (user-supplied)
│   ├── personality.json          # immutable persona
│   ├── personality.lock          # canonical+file SHA256
│   ├── journal/                  # YYYY-MM.md + _current.md mirrors
│   ├── stickers/ gifs/ media_cache/
│
└── tests/                        # TBD (task-16)
```

---

## 5. Settings (`.env`)

| key | default | meaning |
|---|---|---|
| `TG_API_ID` | `23441409` | userbot api id |
| `TG_API_HASH` | `fc2ebed7751be9bc29171b0072b10fed` | userbot api hash |
| `TG_SESSION_NAME` | `session` | kurigram session filename |
| `OPERATOR_ID` | `5624858175` | the only operator's TG user id |
| `OPERATOR_SECRET` | `changeme` | magic prefix for op commands |
| `ONLYSQ_BASE_URL` | `https://api.onlysq.ru/ai/openai` | OnlySq endpoint (no /v1) |
| `ONLYSQ_API_KEY` | *empty* | user fills in |
| `MODEL_REPLY` | `claude-opus-4-6` | speaking model |
| `MODEL_THINK` | `pplx-gemini-3.1-pro` | thinking model |
| `MODEL_EMBED` | `text-embedding-3-small` | embeddings |
| `EMBED_DIM` | `1536` | vec0 column width |
| paths | `data/...`, `logs/` | created at boot |
| `HUMANIZE_MIN_REPLY_DELAY_S` | `2.5` | hard floor before replying |
| `HUMANIZE_MAX_REPLY_DELAY_S` | `900` | ceiling |
| `HUMANIZE_TYPING_CHUNK_S` | `4.5` | typing keepalive cadence |
| `MEDIA_MAX_DOWNLOAD_MB` | `20` | SSRF/size limit |
| `WEB_FETCH_TIMEOUT_S` | `15` | web tool timeout |

---

## 6. Database schema (sqlite, SQLAlchemy 2.x)

ORM tables (`azura.db.models`):

| table | purpose |
|---|---|
| `chats` | id, kind, title, username, importance, opinion (int -100..+100), muted, last_seen_ts, first_contact_ts, meta JSON |
| `users` | id, username, first/last name, is_bot, notes, opinion, first_contact_ts, last_seen_ts, interactions |
| `messages` | per-chat ring buffer: tg_msg_id, from_id, ts, kind, text, reply_to, media_ref, is_self, seen, meta |
| `memory` | unified items across tiers; kind ∈ short/long/daily/global/episodic; topic, content, confidence, importance, decay, ts, last_used_ts, use_count, embed_id |
| `episodes` | when_ts, title, summary, emotion, intensity, embed_id |
| `opinions` | (target_kind ∈ user/chat/topic, target_id) → score ∈ -100..+100, tags JSON, reason |
| `feelings` | (target_kind, target_id, emotion) → intensity 0..1, decay_rate (per hour) |
| `relationships` | (a_id, b_id, chat_id) → kind, strength 0..1 |
| `mood_state` | single row id=1: valence -1..1, arousal/energy/focus/stress/fatigue 0..1 |
| `presence_log` | state, reason, until_ts, started_ts |
| `stickers` | file_id (unique), file_unique_id, set_name, emoji, tags JSON, mood_valence, mood_arousal, description, usage_count, last_used_ts, fits_persona, local_path |
| `gifs` | file_id, file_unique_id, tags, description, usage_count, last_used_ts, fits_persona, local_path |
| `attention_log` | chat_id, started_ts, ended_ts, msgs_read, decided, note |
| `journal` | ts, kind ∈ thought/mood/presence/action/life_event/inner_voice, text, chat_id?, user_id?, meta |
| `kv` | string key → JSON-able string value, updated_ts |

Virtual tables (per-DB, created in `db/schema.py`):

- FTS5: `memory_fts(content, topic, memory_id)`, `episodes_fts(title, summary, episode_id)`, `messages_fts(text, message_id, chat_id)`.
- vec0: `memory_vec(embedding float[N])`, `episodes_vec(...)`, `stickers_vec(...)`, with `N = EMBED_DIM`.

**Important:** user-typed queries are escaped via `fts.fts_quote()` so things like `user:1` don't trip FTS5 column syntax.

### Engine notes

- WAL, `synchronous=NORMAL`, `mmap=256MB`, `cache=-65536`, foreign keys ON.
- sqlite-vec loaded at every connection via a `connect` event hook; aiosqlite's wrapper is unwrapped with `_unwrap()` to access `enable_load_extension`.

---

## 7. Persona JSON

Pydantic schema (`personality.schema.Persona`) — top-level keys:

```
schema_version, seed,
identity { name, age, gender(f|m|nb), city, country, timezone(IANA), occupation, education?, languages[] },
appearance_self_image, background, values[], interests[], dislikes[], secrets[],
traits { 28 entries 0..1 },
derived { attachment_style, humor_style, conflict_style },
speech { register("formal"|"neutral"|"casual"|"slangy"; JSON alias 'register' → field 'speech_register'),
         sentence_length_avg, uses_emoji, emoji_palette[], uses_caps, punctuation,
         typos_rate, favorite_words[], avoid_words[], catchphrases[],
         multi_message_chance, self_correction_chance },
rhythm { wake, sleep, work_blocks[(s,e)], nap_chance, night_owl, weekend_shift_minutes },
social { first_message_per_hour, reply_speed("instant|fast|medium|slow|lazy"),
         ghost_chance, read_no_reply_chance, initiate_close_chance, crowd_attention_span_min },
household { lives_with[], family[{relation,name,age,notes}], pets[], home_notes? },
social_circle { close_friends[], acquaintances[], rivals[], romantic? },
life_events[{when,title,description,impact}], arc { headline, goals_short/long, worries, recent_changes },
boundaries { will_not_discuss[], soft_topics[], triggers[], never_admit_ai=true },
habits[], tastes { category -> items[] }
```

28 traits: `empathy, narcissism, dominance, aggression, adaptiveness, provocativeness, supportiveness, sarcasm, honesty, jealousy, openness, conscientiousness, extraversion, agreeableness, neuroticism, talkativeness, attention_span, patience, curiosity, romanticism, pettiness, grudge_holding, forgiveness_speed, social_battery, playfulness, secrecy, loyalty, impulsivity`.

Generator (`personality.generator.generate(hints, critic_passes=1)`):
1. `_draft()` via `MODEL_THINK` with `response_format=json_object`.
2. `_post_normalize` clamps traits, derives labels, fixes `seed`, `schema_version`.
3. `_critique()` loop (default 1 pass): editor returns `{ok, issues, patch}`; patch is deep-merged.
4. `Persona.model_validate` → `save_persona` writes file + lock.

CLI `init_personality.py`:
- `--interactive` (default): rich prompts for name, gender, age, city, country, tz, occupation, languages, vibe, notes, optional seed.
- `--auto`: no questions, random persona.
- Flags: `--overwrite`, `--critic N`, `--seed N`.

Immutability: `data/personality.lock` stores `sha256(canonical)\nsha256(raw_file_bytes)`; `ensure_immutable()` checks both. Any external edit → `RuntimeError`.

---

## 8. LLM layer

`azura.llm.client`:
- `get_client()` → `AsyncOpenAI(base_url=…onlysq.ru/ai/openai, api_key=…)`. Logs warning if key empty.
- `_with_retries(fn, attempts=4)` exp-backoff on `RateLimitError`, `APIConnectionError`, 5xx `APIError`.
- `chat(model, messages, temperature, tools, tool_choice, response_format)` raw response.
- `chat_text`, `chat_json` (tolerates code fences and `{…}` extraction).
- `embed(model, inputs)`.

`azura.llm.router`:
- `reply_text/reply_json` → `MODEL_REPLY`.
- `think_text/think_json` → `MODEL_THINK` (also used for embed routing's sibling).
- `embed_texts(inputs)` via `MODEL_EMBED`.

Prompts (`azura/llm/templates/*.j2`):
- **persona_outline.j2** — system: design a believable human persona, output strict JSON.
- **persona_user.j2** — exact schema spec for keys & ranges.
- **persona_critic.j2** — editor; returns `{ok, issues, patch}`.
- **system_human.j2** — runtime persona prompt: identity, household, traits, derived, speech rules, hard never-admit-AI clause, mood/situation, tools-policy, output format.
- **inner_voice.j2** — strict JSON: `feeling`, `want_to_reply`, `tone`, `draft_thought`, `should_journal`, `opinion_delta`, `feeling_intensity`.

---

## 9. Memory layer

`azura.memory.service.MemoryService` aggregates tier modules. Key methods:

- `short` — per-chat rolling notes; `add(chat_id, content, …)`, `recent(chat_id)`, `search(chat_id, q)`, `evict_stale()`.
- `long` — facts; `add_fact(content, embedding?)`, `for_chat`, `search`, `search_vec`.
- `daily` — wiped at sleep cycle.
- `global_` — persona-wide.
- `episodic` — `remember(title, summary, emotion, intensity, embedding?)`, `with_user`, `search`, `search_vec`.
- `opinions` — `bump_user/bump_chat/bump_topic`, `proximity(user)`, `chat_aggregate(chat_id, member_ids)`.
- `feelings` — `bump_user/bump_chat`, `dominant_user`, `decay()`.
- `relationships` — `note(a,b, kind, strength)`, `around(user_id)`.
- `forgetting.step()` — applies decay across tiers with different half-lives:
  - short=6h, daily=18h, long=30d, episodic=90d, global=365d.
- `recall_about_user(user_id, query)` and `recall_chat(chat_id)` are the prompt-ready bundles.

Embeddings cached in `embeds.EmbedCache` (in-memory dedup; `get`, `get_many`).

Proximity tiers (from `constants.PROXIMITY_THRESHOLDS`):
- stranger 0 / 0s; acquaintance 10 / 7d; friend 40 / 30d; close 80 / 90d.

---

## 10. Mind layer

Subsystems and their roles:

- **clock**: persona-tz snapshot; phase ∈ {deep_night,…,late_evening,night}; `is_sleep_window`, `is_work_window`.
- **mood (MoodEngine)**:
  - `baseline_for(persona)` from traits.
  - `drift(dt_minutes, clock)` pulls cur→base with phase/work/weekend modifiers + small random shocks.
  - `nudge(valence/arousal/stress)` for instant events.
  - `sleep_reset()` morning recovery.
  - `journal_if_significant()` logs big swings.
- **presence (PresenceEngine)**:
  - `tick(clock, fatigue)` transitions automatically; sleeps in sleep-window with a probabilistic night wakeup tied to impulsivity/night_owl/(1-fatigue).
  - `go_afk(minutes, reason)`, `come_back()`, `set(state)` — all journaled.
- **attention**:
  - Priority tiers (`_tier`): private/bot=0, group/super=1, channel=2, muted_private=3, muted_group=4.
  - Within a tier ranks by unseen×kind_bonus×opinion×importance, with introversion penalty for groups and stress/fatigue penalty.
- **intent (IntentEngine)**:
  - `decide_reply(...)` → reply/read_only/react/later/ignore via trait-weighted probability blend.
  - `decide_first_message(...)` for proactive messaging.
- **triggers**: `detect()` for name variants, @mention, reply-to-self, interest keyword, boundary keyword. `urgency()` collapses into 0..1.
- **inner_voice**: cheap think-model JSON call → feeling/want_to_reply/tone/draft_thought + optional journal & opinion delta.
- **conflict (ConflictEngine)**: picks move (deescalate / stand_ground / escalate / withdraw / passive_aggressive / side_with) by traits + opponent aggression + opinion + topic importance; `apply()` writes opinion+feeling deltas.
- **tails (TailQueue)**: schedules `'oh, also…'` follow-ups; `due()` polled by scheduler.
- **life_events**: random pool (coffee, shower, walk, store, dishes, phone_low, call, food, nap, doomscroll) flips to AFK with reason; journaled.
- **agent (Agent)**:
  - `_system(mood, situation)` renders `system_human.j2`.
  - `run(...)` does N-step OpenAI tool-loop on `MODEL_REPLY`; tool calls dispatched against bound `ToolSpec.fn`.
  - Final output split into 1..N user-facing messages (`_split_final`).
- **scheduler (MindScheduler)**:
  - loops: `heartbeat` (60s±30%), `life_events` (180s±50%), `tails` (30s±30%), `forgetting` (6h±20%).
  - Graceful stop via `_stop` event.

---

## 11. Humanize layer

- **delays.reply_delay(persona, mood, clock, rng, text_len, urgency, in_private)** → `DelayPlan`:
  - `pre_read_s`: base 2–9s × reply_speed × attention_span × fatigue × phase × work × group, clamped to env min/max.
  - `pre_type_s`: 0.4–1.6s × reply_speed.
  - `type_burst_s`: text_len / (3.5 + cons×1.5 − fatigue) + jitter, ≥ 0.8s.
  - `after_send_s`: 0.6–2.4s.
- **typing.type_with_ticks** sends keepalives every `HUMANIZE_TYPING_CHUNK_S` with rare micro-pauses.
- **typos**: per-word probability (rate), 4 ops (swap/drop/double/neighbor), ru/en QWERTY+ЙЦУКЕН maps; `correction_messages()` emits `*word` followups.
- **splitter.split_reply** honours `multi_message_chance`; soft-splits on commas/conjunctions when no terminators.
- **style_diversity.StyleDiversity** windowed n-gram overlap to refuse repeat phrasings.
- **anti_detect**:
  - `has_chatbot_smell(text)`: ru+en patterns ("as an AI", "language model", "я нейросеть", "чем я могу помочь", etc.) + assistant-style prefixes.
  - `sanitize(text, persona)` strips offending lines and `persona.speech.avoid_words`.
- **backpressure**: global min gap + per-chat per-minute cap.

---

## 12. Tools registry (32 tools, 9 families)

Built by `tools.builder.build_registry(ctx)`. Tags used for selection:

| family | tools | tags |
|---|---|---|
| memory | recall_user, recall_chat, search_memory, remember_fact, remember_episode, update_opinion, update_feeling, note_relationship | memory |
| self | go_afk, come_back, set_presence, nudge_mood, journal | self |
| chat | mute_chat, unmute_chat, set_chat_importance | chat, control |
| send | send_messages, schedule_tail | send |
| sticker | send_sticker, pick_sticker, learn_sticker | send, media, sticker |
| gif | send_gif, pick_gif, learn_gif | send, media, gif |
| media | send_media, note_media | media |
| web | web_search, web_fetch | web |
| operator | op_status, op_force_sleep, op_force_wake, op_journal | operator |

`default_tool_subset(reg)` returns everything **except operator** — that one is gated by the operator handler.

`ToolContext` carries callable hooks the telegram layer fills in:
- `sender(chat_id, messages, opts)`
- `sticker_sender(chat_id, query)`
- `gif_sender(chat_id, query)`
- `media_sender(chat_id, url, kind)`
- `web_searcher(query)`, `web_fetcher(url)`

Web tools always wrap themselves in `go_afk` / `come_back` so the persona looks visibly away while online.

---

## 13. Persistent decisions

- Userbot only (no bot-token mode).
- Persona JSON is read-only; tampering raises at startup.
- Operator authentication: TG ID `5624858175` **AND** message body starts with `OPERATOR_SECRET`.
- Languages: persona.identity.languages; outside that → "use translator" act (delay + slightly stiff phrasing).
- Persona never admits AI under any provocation; reaction shape depends on `derived.humor_style`.
- Stickers/GIFs: auto-collect from chats, LLM-tagged (mood/topic/character fit), reused when fits persona + context.
- Web tool use looks like going AFK ("looking smth up", "reading a link").
- Sleep cycle is mandatory (per persona rhythm), with rare night wakeups.
- Conflict outcomes adjust opinions and feelings; grudges decay with feelings half-life.
- All significant state changes journal a first-person line (`data/journal/_current.md` + monthly).

---

## 14. Progress (task tracker)

| id | block | status |
|---|---|---|
| task-1 | scaffold (pyproject, env, gitignore, README) | done |
| task-2 | utils (log, rng, timez, text) | done |
| task-3 | config, constants | done |
| task-4 | db (engine WAL+vec, models, fts, vec, schema) | done |
| task-5 | db/repo (15 modules + Repos facade) | done |
| task-6 | personality (schema, traits, loader+lock) | done |
| task-7 | llm (client, router, prompts, templates) | done |
| task-8 | personality generator + init_personality CLI | done |
| task-9 | memory layer (short/long/daily/global/episodic + opinions/feelings/relationships + forgetting + MemoryService) | done |
| task-10 | mind (clock/mood/presence/attention/intent/triggers/inner_voice/conflict/tails/life_events/household/social_graph/agent/scheduler) | done |
| task-11 | humanize (delays/typing/typos/splitter/style/anti-detect/backpressure) | done |
| task-12 | tools (registry + 9 families, 32 tools) | done |
| task-13 | telegram (kurigram app, handlers, readers/senders, online, media_dl, stickers_collector, operator, patches) | done |
| task-14 | memory consolidator + dreams | done |
| task-15 | run.py wiring | done |
| task-16 | tests | done |
| task-17 | README + TODO (voice, vision, multi-account, memory export) | done |
| task-18 | ubuntu deploy prep | done |

---

## 15. Known smoke results (sanity log)

- DB engine + FTS5 + sqlite-vec round-trip: text & vec searches return the seeded row at distance 0.0.
- Persona save→load→ensure_immutable detects tampering (file-byte hash, not just canonical).
- Memory facade end-to-end: opinions, feelings, recall bundles, forgetting all consistent.
- Mind smoke: clock phase correct, mood drift bounded, presence transitions sleep at 03:00, attention orders private→group→channel→muted_private→muted_group, conflict picks stand_ground at agr=0.6/pat=0.5, tails deliver, intent gives `reply 0.78` on a friendly DM.
- Tools wiring: 32 tools registered, default subset 28, key tools (`update_opinion`, `update_feeling`, `journal`, `go_afk`, `nudge_mood`) exercise the DB and engines correctly.

---

## 16. Telegram layer (task-13 — done)

Key points:

- `telegram/handlers.py::Dispatcher` is bound via `MessageHandler(dispatcher.on_message, filters.all)`. It uses a **per-chat asyncio.Lock** so handler runs for the same chat serialize.
- Each dispatch opens a **fresh AsyncSession** from the shared `async_sessionmaker`, builds a `Repos` + `MemoryService` against it, and commits once at the end.
- Persisted first (always), then operator-handle shortcut, then mind/intent decision, then optional agent.run with tools, then Sender.
- Sender does: anti-detect sanitize → split_reply → typos → typing-keepalive ticks → per-message backpressure → optional `*word` corrections → after-send pause.
- Reader.cycle obeys `Presence`: no reads when asleep/offline/afk; otherwise walks the priority queue with 1.5–6s gaps between chats and calls `client.read_chat_history(chat_id)`.
- `media_dl.send_url(client, chat_id, url, kind)`: streams URL → temp file with size+scheme+SSRF guards, then sends as photo/video/animation/document by extension when `kind=auto`.
- `stickers_collector` triggers on `msg.sticker` / `msg.animation`, persists file_id and queues an async LLM tag pass that fills tags/desc/mood/fits_persona.
- `operator.handle` accepts only DMs from `OPERATOR_ID`, body must start with `OPERATOR_SECRET`. Commands: `status`, `sleep`, `wake`, `journal [N]`, `pause`, `resume`.
- `web_impl.py` (in `tools/`): DDG html search + safe `fetch_text` (SSRF guard); both are wrapped by `web_tools` in `go_afk`/`come_back` so the persona looks visibly busy.

## 17. Consolidation + dreams (task-14 — done)

- `memory/consolidator.py::Consolidator.consolidate_chat(chat_id)` reads up to 60 recent short-term notes, asks `MODEL_THINK` (via `consolidate.j2`) for: stable facts, opinion deltas, feeling bumps, episodes. Persists everything with embeddings (via EmbedCache). `consolidate_all_active()` iterates over every chat with short-term notes.
- `memory/dreams.py::Dreams.run()` (called by scheduler when presence == asleep) feeds recent episodes + top positives/negatives + mood snapshot to `MODEL_THINK` (via `dream.j2`). Persists: global_keeps, opinion_softens, feeling_softens, episode_reframes, dream_journal line. Calls `mood.sleep_reset()` afterwards.
- Scheduler periods: `consolidate` ~1h, `dream` ~15m (only fires when asleep).

## 18. Entry point (task-15 — done)

- `azura/run.py::main()` (also `azura` console script) does:
  1. Load `Settings` (warns if `ONLYSQ_API_KEY` empty).
  2. `ensure_immutable(persona, lock)` — abort if persona missing or tampered.
  3. `init_engine(db_path)` + `init_schema(embed_dim)`.
  4. Build shared `Rng`, `Backpressure`, `StyleDiversity`, `TailQueue`.
  5. Build kurigram `Client` via `make_client(s)`.
  6. Build `Dispatcher` + register a single `MessageHandler(dispatcher.on_message, filters.all)`.
  7. Wire callbacks for the scheduler:
     - `on_tail(chat_id, text)` opens a fresh session and sends via `Sender`.
     - `on_status(state)` opens a session, reads presence, and calls `push_status` to update TG online state.
  8. Build `MindScheduler` (heartbeat, life_events, tails, forgetting, consolidate, dream) and `ReaderLoop` (attention pass every ~90s with jitter).
  9. `client.start()` → `get_me()` log → `scheduler.start()` → `reader_loop.start()`.
  10. Wait on `stop_event` (SIGINT/SIGTERM on POSIX, KeyboardInterrupt elsewhere).
  11. Graceful shutdown: reader_loop → scheduler → client.stop() → dispose_engine().

### How to run end-to-end

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .[dev]

copy .env.example .env
# fill ONLYSQ_API_KEY in .env

python -m azura.init_personality --interactive
python -m azura.run
```

On first start kurigram will ask for phone/code interactively in stdin (it writes `data/session.session`). Subsequent starts use the saved session.

## 19. Docs + deploy (task-17 + task-18 — done)

- **README.md** — full intro: what makes it not feel like a bot, project layout, quick-start (Win/Linux), config keys, CLI flags, operator commands, immutability, on-disk layout, troubleshooting.
- **TODO.md** — roadmap: near-term (tests, vision-input, sticker thumbnails, operator extensions, read-no-reply backoff), mid-term (voice, vision-gen, reactions, translator act), long-term (multi-account, memory export/import, web UI, cluster, ageing, periodic self-rewrite), DX (alembic, mypy, pre-commit, prometheus).
- **DEPLOY.md** — Ubuntu deploy procedure: system packages, service user, code+venv, .env, persona generation, first interactive TG login, systemd unit, updates, backups, hardening.
- **deploy/** — artifacts:
  - `azura.service` (systemd unit, hardened: NoNewPrivileges, ProtectSystem=strict, ProtectHome, etc; ReadWritePaths = data + logs only; Restart=on-failure).
  - `install.sh` (one-shot installer; takes REPO_URL, optional APP_ROOT/APP_USER/PYTHON_BIN).
  - `deploy/README.md` (pointer to the top-level DEPLOY.md).

## 20. Test suite (task-16 — done)

**96 tests, all green, ~4s wall time.**

Layout:

```
tests/
├── conftest.py             # fixtures: per-test sqlite (file path, sqlite-vec needs file), session, repos, MemoryService, persona, Rng(1337)
├── factories.py            # make_persona(**overrides) — fully-validated Persona for tests
├── unit/                   # utils (rng, timez, text), db+repos+FTS+vec, persona schema/lock, MemoryService bundles
├── humanity/               # delays distribution + bounds + urgency/fatigue/night effects; typos+split+style+anti_detect
├── activity/               # clock phases, MoodEngine drift+nudge+sleep_reset, PresenceEngine auto-sleep/wake/AFK/busy, Attention priority + score, Intent+Triggers stats over 60 seeds
├── social/                 # opinions clamp, chat aggregate, proximity gating by age, dominant feeling, relationship round-trip, conflict moves
└── integration/
    ├── _fakes.py           # FakeClient (records sent_messages/read_history/typing/reactions), FakeUser/FakeChat/FakeMessage, FakePyrogramChatType
    ├── test_sender.py      # full humanize pipeline against FakeClient: reads, splits, blocks chatbot phrases
    └── test_dispatcher.py  # end-to-end: incoming Message → record → intent (forced) → agent (mocked) → sender; verifies reply/read-only/asleep paths
```

Key conventions:

- `pytest-asyncio` is in `auto` mode (set in `pyproject`); the session-scoped `event_loop` fixture is shared.
- The `db` fixture creates a per-test sqlite file under `tmp_path` and re-runs `init_schema(embed_dim=8)`; it tears down via `dispose_engine()`.
- Integration tests inject `monkeypatch` to make `asyncio.sleep` a no-op in `azura.humanize.typing` and `azura.telegram.senders`, so humanized flows still execute but in milliseconds.
- `Agent.run` and `IntentEngine` are monkey-patched in `test_dispatcher.py` (decision and final messages are hard-coded), so dispatcher tests don't call OnlySq.
- Statistical tests (intent over 60 seeds, delays over 200 samples) verify directionality and spread, not specific magic numbers.

Run the whole suite:

```powershell
python -m pytest -q
```

## 21. All tasks closed

Project is feature-complete. Future work: see `TODO.md` (voice, vision-input/gen, multi-account, memory export, reactions, web UI, ageing, periodic self-rewrite, alembic, mypy, prometheus, pre-commit).
