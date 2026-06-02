"""Standalone CLI: run the account bootstrap (or force re-bootstrap).

Usage:
  python -m azura.bootstrap_cli           # respect detection logic
  python -m azura.bootstrap_cli --force   # always regenerate
  python -m azura.bootstrap_cli --skip-photo

Requires the main service to be stopped (kurigram session is exclusive).
"""
from __future__ import annotations

import argparse
import asyncio
import sys

from rich.console import Console
from rich.panel import Panel

from azura.config import get_settings
from azura.db.engine import dispose_engine, get_sessionmaker, init_engine
from azura.db.repo import Repos
from azura.db.schema import init_schema
from azura.personality.loader import ensure_immutable
from azura.telegram.app import make_client
from azura.telegram.bootstrap import run as run_bootstrap
from azura.utils.log import setup_logging

C = Console()


async def _amain(args) -> int:
    s = get_settings()
    setup_logging(level=s.log_level, log_dir=s.log_dir)

    if not s.onlysq_api_key:
        C.print("[red]ONLYSQ_API_KEY missing in .env[/red]")
        return 2
    if not s.personality_path.exists():
        C.print(f"[red]persona missing: {s.personality_path}[/red]")
        return 3
    persona = ensure_immutable(s.personality_path, s.personality_lock_path)
    C.print(Panel.fit(
        f"[bold magenta]bootstrap[/bold magenta]\n"
        f"persona: [cyan]{persona.identity.name}[/cyan] ({persona.identity.age}/{persona.identity.gender})\n"
        f"force={args.force} skip_photo={args.skip_photo}",
        border_style="magenta",
    ))

    init_engine(s.db_path)
    await init_schema(embed_dim=s.embed_dim)
    sm = get_sessionmaker()

    client = make_client(s)
    await client.start()
    try:
        me = await client.get_me()
        C.print(f"[dim]current TG: id={me.id} first={me.first_name!r} last={me.last_name!r} "
                f"username={me.username!r}[/dim]")

        async with sm() as session:
            r = Repos(session)
            result = await run_bootstrap(client, r, persona,
                                          force=args.force, skip_photo=args.skip_photo)
            await session.commit()
        C.print(f"[green]bootstrap result:[/green] {result}")
    finally:
        await client.stop()
        await dispose_engine()
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(prog="azura-bootstrap")
    ap.add_argument("--force", action="store_true",
                    help="ignore detection logic, regenerate even if already done")
    ap.add_argument("--skip-photo", action="store_true",
                    help="only names/bio/username, no portrait generation")
    args = ap.parse_args()
    try:
        return asyncio.run(_amain(args))
    except KeyboardInterrupt:
        return 1


if __name__ == "__main__":
    sys.exit(main())
