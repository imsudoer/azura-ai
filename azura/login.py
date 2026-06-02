"""Interactive Telegram first-login: writes data/session.session for the userbot.

Run once before deploying. Idempotent — re-running on an existing valid session
just verifies it and prints the active account info.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from azura.config import get_settings
from azura.telegram.app import make_client
from azura.utils.log import setup_logging

C = Console()


async def _amain() -> int:
    """Async entry: build client, log in, verify, persist session."""
    s = get_settings()
    setup_logging(level=s.log_level, log_dir=s.log_dir)

    session_file = (Path(s.session_path).parent / f"{s.tg_session_name}.session")
    existed = session_file.exists()

    C.print(Panel.fit(
        f"[bold magenta]azura — Telegram login[/bold magenta]\n"
        f"session file: [cyan]{session_file}[/cyan]\n"
        f"status: [{'green' if existed else 'yellow'}]"
        f"{'already exists — will verify' if existed else 'new login'}[/]",
        border_style="magenta",
    ))

    if not s.tg_api_id or not s.tg_api_hash:
        C.print("[red]TG_API_ID / TG_API_HASH missing in .env[/red]")
        return 2

    client = make_client(s)
    try:
        await client.start()
    except Exception as e:
        C.print(f"[red]login failed: {e}[/red]")
        return 3

    try:
        me = await client.get_me()
    except Exception as e:
        C.print(f"[red]get_me failed after start: {e}[/red]")
        await client.stop()
        return 4

    t = Table(title="Telegram session", show_lines=False)
    t.add_column("field", style="cyan")
    t.add_column("value", style="white")
    t.add_row("id", str(me.id))
    t.add_row("first_name", me.first_name or "")
    t.add_row("last_name", me.last_name or "")
    t.add_row("username", f"@{me.username}" if me.username else "(none)")
    t.add_row("phone", getattr(me, "phone_number", "") or "")
    t.add_row("is_premium", str(bool(getattr(me, "is_premium", False))))
    t.add_row("session_file", str(session_file))
    C.print(t)

    await client.stop()
    C.print(f"[green]session saved at {session_file}[/green]")
    C.print("[dim]you can now run: python -m azura.run[/dim]")
    return 0


def main() -> int:
    """Sync wrapper used by the `azura-login` console script."""
    try:
        return asyncio.run(_amain())
    except KeyboardInterrupt:
        C.print("[yellow]aborted[/yellow]")
        return 1


if __name__ == "__main__":
    sys.exit(main())
