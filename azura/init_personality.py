"""CLI to generate the immutable persona JSON: --interactive (default) or --auto."""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, IntPrompt, Prompt
from rich.table import Table

from azura.config import get_settings
from azura.personality.generator import generate
from azura.personality.loader import save_persona
from azura.utils.log import setup_logging

C = Console()


def _ask_languages(default: str = "ru") -> list[str]:
    raw = Prompt.ask(
        "[bold]Languages the persona speaks natively[/bold] (comma-separated ISO codes)",
        default=default,
    )
    out = [x.strip().lower() for x in raw.split(",") if x.strip()]
    return out or ["ru"]


def _ask_vibe() -> str:
    return Prompt.ask(
        "[bold]Overall vibe[/bold] (free-form, e.g. 'sarcastic introvert, late-night coder, soft underneath')",
        default="curious, slightly chaotic, warm with close friends, cold to strangers",
    )


def _interactive_hints() -> dict[str, Any]:
    C.print(Panel.fit("[bold magenta]Persona builder — interactive[/bold magenta]\nFill what you care about, leave the rest empty.", border_style="magenta"))

    hints: dict[str, Any] = {}

    name = Prompt.ask("Name (or blank to let the model pick)", default="")
    if name:
        hints["name"] = name

    gender = Prompt.ask("Gender", choices=["f", "m", "nb", "?"], default="?")
    if gender != "?":
        hints["gender"] = gender

    age = IntPrompt.ask("Age (14..80, 0 to skip)", default=0)
    if age:
        hints["age"] = age

    city = Prompt.ask("City (blank to skip)", default="")
    if city:
        hints["city"] = city

    country = Prompt.ask("Country (blank to skip)", default="")
    if country:
        hints["country"] = country

    tz = Prompt.ask("IANA timezone (blank to skip)", default="")
    if tz:
        hints["timezone"] = tz

    occupation = Prompt.ask("Occupation (blank to skip)", default="")
    if occupation:
        hints["occupation"] = occupation

    hints["languages"] = _ask_languages()
    hints["vibe"] = _ask_vibe()

    extra = Prompt.ask("Anything else? (free-form notes, blank to skip)", default="")
    if extra:
        hints["notes"] = extra

    seed_in = Prompt.ask("Random seed (blank for random)", default="")
    if seed_in.strip().isdigit():
        hints["seed"] = int(seed_in.strip())

    return hints


def _show_summary(p) -> None:
    t = Table(title="Persona summary", show_lines=False)
    t.add_column("field", style="cyan")
    t.add_column("value", style="white")
    t.add_row("name", p.identity.name)
    t.add_row("age/gender", f"{p.identity.age} / {p.identity.gender}")
    t.add_row("city", f"{p.identity.city}, {p.identity.country} ({p.identity.timezone})")
    t.add_row("occupation", p.identity.occupation)
    t.add_row("languages", ", ".join(p.identity.languages))
    t.add_row("derived", ", ".join(f"{k}={v}" for k, v in p.derived.items()))
    t.add_row("arc", p.arc.headline)
    C.print(t)
    top_traits = sorted(p.traits.items(), key=lambda kv: kv[1], reverse=True)[:8]
    C.print("[bold]Top traits[/bold]: " + ", ".join(f"{k}={v:.2f}" for k, v in top_traits))


async def _run(hints: dict[str, Any], *, critic: int, overwrite: bool) -> int:
    s = get_settings()
    if not s.onlysq_api_key:
        C.print("[red]ONLYSQ_API_KEY is empty in .env — fill it and re-run.[/red]")
        return 2
    if s.personality_path.exists() and not overwrite:
        C.print(f"[yellow]Persona already exists at {s.personality_path}.[/yellow]")
        if not Confirm.ask("Overwrite?", default=False):
            return 1

    C.print("[dim]Asking the model to design a persona... this can take a minute.[/dim]")
    p = await generate(hints, critic_passes=critic)
    _show_summary(p)

    if not overwrite and not Confirm.ask("Save this persona as immutable?", default=True):
        C.print("[yellow]Aborted.[/yellow]")
        return 1

    h = save_persona(p, s.personality_path, s.personality_lock_path)
    C.print(f"[green]Saved {s.personality_path}[/green]  hash=[bold]{h[:12]}[/bold]")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Entry point for `python -m azura.init_personality` or `azura-init`."""
    setup_logging(level=os.getenv("LOG_LEVEL", "INFO"))
    ap = argparse.ArgumentParser(prog="azura-init", description="Generate the immutable persona JSON")
    ap.add_argument("--auto", action="store_true", help="non-interactive, random persona")
    ap.add_argument("--interactive", action="store_true", help="interactive mode (default)")
    ap.add_argument("--overwrite", action="store_true", help="skip overwrite confirmation")
    ap.add_argument("--critic", type=int, default=1, help="critic passes (0 to skip)")
    ap.add_argument("--seed", type=int, default=None, help="explicit RNG seed")
    args = ap.parse_args(argv)

    interactive = args.interactive or not args.auto
    hints: dict[str, Any] = {}
    if args.seed is not None:
        hints["seed"] = args.seed
    if interactive:
        hints.update(_interactive_hints())
    else:
        hints.setdefault("languages", ["ru"])

    return asyncio.run(_run(hints, critic=args.critic, overwrite=args.overwrite))


if __name__ == "__main__":
    sys.exit(main())
