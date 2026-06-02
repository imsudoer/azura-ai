"""Entry point: boots DB, persona, mind, telegram, scheduler, runs forever."""

from __future__ import annotations

import asyncio
import signal
import sys
from pathlib import Path

from azura.config import get_settings
from azura.db.engine import dispose_engine, get_sessionmaker, init_engine
from azura.db.schema import init_schema
from azura.humanize.backpressure import Backpressure
from azura.humanize.style_diversity import StyleDiversity
from azura.mind.mood import MoodEngine
from azura.mind.presence import PresenceEngine
from azura.mind.scheduler import MindScheduler
from azura.mind.tails import TailQueue
from azura.personality.loader import ensure_immutable
from azura.telegram.app import make_client
from azura.telegram.handlers import Dispatcher, register
from azura.telegram.online import push_status
from azura.telegram.reader_loop import ReaderLoop
from azura.utils.log import get_logger, setup_logging
from azura.utils.rng import Rng

log = get_logger("run")


async def _amain() -> int:
    """Async main loop: build everything, register handlers, run until interrupted."""
    s = get_settings()
    setup_logging(level=s.log_level, log_dir=s.log_dir)
    log.info("azura-ai starting up")

    if not s.onlysq_api_key:
        log.warning(
            "ONLYSQ_API_KEY is empty — LLM calls will fail until you set it in .env"
        )

    if not s.personality_path.exists():
        log.error(
            "personality file missing: {}. Run: python -m azura.init_personality --interactive",
            s.personality_path,
        )
        return 2

    try:
        persona = ensure_immutable(s.personality_path, s.personality_lock_path)
    except Exception as e:
        log.error("persona load failed: {}", e)
        return 3
    log.info(
        "persona loaded: {} ({} {})",
        persona.identity.name,
        persona.identity.age,
        persona.identity.gender,
    )

    init_engine(s.db_path)
    await init_schema(embed_dim=s.embed_dim)
    sm = get_sessionmaker()

    rng = Rng()
    bp = Backpressure()
    style = StyleDiversity(window=80, n=4)

    client = make_client(s)

    tails = TailQueue(persona, rng=rng)

    dispatcher = Dispatcher(
        client=client,
        persona=persona,
        sessionmaker=sm,
        settings=s,
        rng=rng,
        backpressure=bp,
        style=style,
        mood_engine_factory=lambda p, m, *, rng: MoodEngine(p, m, rng=rng),
        presence_engine_factory=lambda p, m, *, rng: PresenceEngine(
            p, m, rng=rng, tg_client=client
        ),
    )
    register(dispatcher, client)

    async def on_tail(chat_id: int, text: str) -> None:
        if not text:
            return
        async with sm() as session:
            from azura.db.repo import Repos
            from azura.memory.service import MemoryService
            from azura.mind.clock import snapshot as _snap

            r = Repos(session)
            m = MemoryService(r)
            mood_view = await MoodEngine(persona, m, rng=rng).now()
            clk = _snap(persona)
            from azura.telegram.senders import Sender

            sender = Sender(
                client, persona=persona, memory=m, rng=rng, backpressure=bp, style=style
            )
            await sender.send(
                chat_id, [text], mood=mood_view, clock=clk, in_private=True, urgency=0.1
            )
            await session.commit()

    async def on_status(state: str) -> None:
        async with sm() as session:
            from azura.db.repo import Repos
            from azura.memory.service import MemoryService

            r = Repos(session)
            m = MemoryService(r)
            view = await PresenceEngine(persona, m, rng=rng).current()
            await push_status(client, view)

    scheduler = MindScheduler(
        persona=persona,
        sessionmaker=sm,
        rng=rng,
        tails=tails,
        on_tail=on_tail,
        on_status=on_status,
    )
    reader_loop = ReaderLoop(client=client, persona=persona, sessionmaker=sm, rng=rng)

    stop_event = asyncio.Event()

    def _on_signal(*_args):
        log.info("shutdown signal received")
        stop_event.set()

    if sys.platform != "win32":
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, _on_signal)

    await client.start()
    try:
        me = await client.get_me()
        log.info(
            "telegram session up: id={} name={} username={}",
            me.id,
            me.first_name,
            me.username,
        )
    except Exception as e:
        log.warning("get_me failed: {}", e)

    try:
        from azura.telegram.bootstrap import run as run_bootstrap

        async with sm() as boot_session:
            from azura.db.repo import Repos

            br = Repos(boot_session)
            bs = await run_bootstrap(client, br, persona)
            await boot_session.commit()
        if not bs.get("skipped"):
            log.info("account bootstrap applied: {}", bs)
    except Exception:
        log.exception("account bootstrap failed (continuing)")

    try:
        async with sm() as _boot_s:
            from azura.db.repo import Repos as _R
            from azura.memory.service import MemoryService as _M
            from azura.telegram.tg_presence import apply_to_telegram as _apply

            _r = _R(_boot_s)
            _m = _M(_r)
            _cur = await PresenceEngine(
                persona, _m, rng=rng, tg_client=client
            ).current()
            await _apply(client, _cur.state)
    except Exception:
        log.exception("failed to push initial presence to telegram")

    from azura.telegram.tg_presence import PresenceKeeper

    async def _get_state():
        async with sm() as ks:
            from azura.db.repo import Repos as _R2
            from azura.memory.service import MemoryService as _M2

            _r2 = _R2(ks)
            _m2 = _M2(_r2)
            v = await PresenceEngine(persona, _m2, rng=rng).current()
            return v.state

    presence_keeper = PresenceKeeper(client, _get_state, interval_s=10.0)
    await presence_keeper.start()

    await scheduler.start()
    await reader_loop.start()
    log.info("azura-ai online — listening")
    try:
        await stop_event.wait()
    except KeyboardInterrupt:
        pass
    finally:
        log.info("shutting down...")
        await presence_keeper.stop()
        await reader_loop.stop()
        await scheduler.stop()
        await client.stop()
        await dispose_engine()
        log.info("bye.")
    return 0


def main() -> int:
    """Sync entry for the `azura` console script."""
    try:
        return asyncio.run(_amain())
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
