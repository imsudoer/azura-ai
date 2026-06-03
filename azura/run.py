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

    from azura.telegram.typing_watcher import TypingWatcher

    async def _on_orphan_typing(chat_id: int, user_id: int, duration: float) -> None:
        async with sm() as ks:
            from azura.db.repo import Repos as _R
            from azura.memory.service import MemoryService as _MS
            _r = _R(ks); _m = _MS(_r)
            cur = await PresenceEngine(persona, _m, rng=rng).current()
        if cur.state.value in ("asleep", "offline", "afk", "busy"):
            log.info(
                "orphan typing chat={} user={} duration={:.1f}s SKIP (presence={})",
                chat_id, user_id, duration, cur.state.value,
            )
            return
        log.info(
            "orphan typing chat={} user={} duration={:.1f}s",
            chat_id, user_id, duration,
        )

    async def _on_typing_start(chat_id: int, user_id: int) -> None:
        log.debug("someone typing chat={} user={}", chat_id, user_id)

    typing_watcher = TypingWatcher(
        on_typing_start=_on_typing_start,
        on_orphan_typing=_on_orphan_typing,
        expire_s=12.0,
        min_orphan_duration_s=3.0,
    )
    dispatcher.typing_watcher = typing_watcher
    await typing_watcher.start()

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

    from azura.telegram.tg_presence import PresenceKeeper, force_offline
    try:
        await force_offline(client, reason="boot")
    except Exception:
        log.exception("initial force_offline failed")
    presence_keeper = PresenceKeeper(client, interval_s=20.0)
    await presence_keeper.start()

    from azura.telegram.peer_cache import install_peer_cache, warm_cache
    install_peer_cache(client)
    try:
        async with sm() as _ws:
            from azura.db.repo import Repos as _WR
            _wr = _WR(_ws)
            _active = await _wr.chats.all_active()
            _ids = [c.id for c in _active]
        if _ids:
            from azura.telegram.tg_presence import go_online_briefly
            await go_online_briefly(client, seconds=10.0, reason="peer_cache_warm")
            warm_cache(client, _ids)
    except Exception:
        log.exception("peer cache warm failed")

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
        try:
            await typing_watcher.stop()
        except Exception:
            pass
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
