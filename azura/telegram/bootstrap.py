"""First-start bootstrap: generate a coherent Telegram profile from the persona.

Detects whether the account looks "fresh" (no name set / username matches TG default
/ no profile photo) or whether the user forced it via flag. On bootstrap:
- Ask the think model for first_name / last_name / bio / username candidates.
- Apply update_profile + set_username (trying candidates in order until free).
- Generate a portrait via Imagen and set it as the profile photo.

Stores `bootstrap.done` in kv to remember it ran. The CLI flag --redo overrides.
"""
from __future__ import annotations

import orjson
from typing import Any

from pyrogram import Client

from azura.config import get_settings
from azura.db.repo import Repos
from azura.llm import imagen
from azura.llm.prompts import render
from azura.llm.router import think_json
from azura.personality.schema import Persona
from azura.telegram import account as acct
from azura.utils.log import get_logger

log = get_logger("tg.bootstrap")


_KV_DONE = "bootstrap.done"
_KV_NAMES = "bootstrap.names"
_KV_PHOTO = "bootstrap.photo"


async def is_done(repos: Repos) -> bool:
    """Check the kv flag."""
    v = await repos.kv.get_json(_KV_DONE)
    return bool(v)


async def mark_done(repos: Repos, payload: dict) -> None:
    await repos.kv.set_json(_KV_DONE, {"ts": int(__import__("time").time()), **payload})


def _persona_brief_for_names(p: Persona) -> dict:
    return {
        "identity": p.identity.model_dump(),
        "appearance_self_image": p.appearance_self_image,
        "interests": p.interests[:10],
        "speech_register": p.speech.speech_register,
        "humor_style": p.derived.get("humor_style"),
        "values": p.values[:5],
        "tastes": p.tastes,
        "arc_headline": p.arc.headline,
    }


async def generate_names(persona: Persona) -> dict:
    """Ask think-model for first_name/last_name/bio/username_candidates."""
    sys = render("account_bootstrap.j2")
    usr = "Persona:\n" + orjson.dumps(_persona_brief_for_names(persona),
                                       option=orjson.OPT_INDENT_2).decode()
    out = await think_json(
        [{"role": "system", "content": sys}, {"role": "user", "content": usr}],
        temperature=0.7, max_tokens=600,
        response_format={"type": "json_object"},
    )
    out["first_name"] = str(out.get("first_name") or persona.identity.name).strip()[:64]
    out["last_name"] = (str(out["last_name"]).strip()[:64] if out.get("last_name") else None)
    out["bio"] = str(out.get("bio") or "").strip()[:70]
    cands = out.get("username_candidates") or []
    out["username_candidates"] = [str(c).strip().lstrip("@") for c in cands if c][:10]
    return out


async def _apply_names(client: Client, names: dict) -> tuple[bool, str | None]:
    """Apply first/last/bio. Then walk username candidates until one is free."""
    ok = await client.update_profile(
        first_name=names.get("first_name"),
        last_name=names.get("last_name") or "",
        bio=names.get("bio") or "",
    )
    chosen: str | None = None
    for cand in names.get("username_candidates") or []:
        try:
            available = await client.check_username(cand)
        except Exception as e:
            log.info("check_username {} failed: {}", cand, e)
            continue
        if available:
            try:
                await client.set_username(cand)
                chosen = cand
                break
            except Exception as e:
                log.info("set_username {} failed: {}", cand, e)
                continue
    return bool(ok), chosen


def _persona_brief_for_portrait(p: Persona) -> dict:
    return {
        "identity": {
            "age": p.identity.age, "gender": p.identity.gender,
            "city": p.identity.city, "country": p.identity.country,
            "occupation": p.identity.occupation,
        },
        "appearance_self_image": p.appearance_self_image,
        "speech_register": p.speech.speech_register,
        "humor_style": p.derived.get("humor_style"),
        "interests": p.interests[:6],
        "current_arc": p.arc.headline,
        "season_hint": "",
    }


async def build_portrait_prompt(persona: Persona) -> tuple[str, str]:
    """Generate prompt + negative prompt for a realistic candid portrait."""
    sys = render("portrait_prompt.j2")
    usr = "Persona:\n" + orjson.dumps(_persona_brief_for_portrait(persona),
                                       option=orjson.OPT_INDENT_2).decode()
    out = await think_json(
        [{"role": "system", "content": sys}, {"role": "user", "content": usr}],
        temperature=0.9, max_tokens=900,
        response_format={"type": "json_object"},
    )
    prompt = str(out.get("prompt") or "").strip()
    negative = str(out.get("negative") or "").strip()
    return prompt, negative


async def generate_and_set_photo(client: Client, persona: Persona) -> dict:
    """Generate a portrait via Imagen and set it as profile photo. Returns status dict."""
    try:
        prompt, negative = await build_portrait_prompt(persona)
    except Exception as e:
        log.warning("portrait prompt build failed: {}", e)
        return {"ok": False, "stage": "prompt", "reason": str(e)}
    log.info("portrait prompt ({} chars)", len(prompt))
    try:
        paths = await imagen.generate(prompt=prompt + ("\n\nNEGATIVE: " + negative if negative else ""), n=1)
    except Exception as e:
        return {"ok": False, "stage": "imagen", "reason": str(e)}
    if not paths:
        return {"ok": False, "stage": "imagen", "reason": "empty result"}
    photo_path = paths[0]
    try:
        res = await acct.set_profile_photo(client, photo_path)
    except Exception as e:
        return {"ok": False, "stage": "set_photo", "reason": str(e), "path": str(photo_path)}
    return {"ok": bool(res.get("ok")), "path": str(photo_path)}


async def needs_bootstrap(client: Client, repos: Repos, *, force: bool = False) -> bool:
    """Decide whether to run the bootstrap."""
    if force:
        return True
    if await is_done(repos):
        return False
    try:
        me = await client.get_me()
    except Exception:
        return True
    fn = (me.first_name or "").strip()
    if not fn or fn.lower() in ("", "user", "telegram"):
        return True
    photos = []
    try:
        async for p in client.get_chat_photos("me", limit=1):
            photos.append(p)
    except Exception:
        pass
    if not photos:
        return True
    return False


async def run(
    client: Client, repos: Repos, persona: Persona, *, force: bool = False,
    skip_photo: bool = False,
) -> dict:
    """Run the full bootstrap and return a status dict."""
    if not await needs_bootstrap(client, repos, force=force):
        return {"skipped": True, "reason": "already bootstrapped"}

    names = await generate_names(persona)
    await repos.kv.set_json(_KV_NAMES, names)
    profile_ok, chosen_username = await _apply_names(client, names)
    log.info("bootstrap names: profile_ok={} username={}", profile_ok, chosen_username)

    photo_result: dict = {"skipped": True}
    if not skip_photo:
        photo_result = await generate_and_set_photo(client, persona)
        await repos.kv.set_json(_KV_PHOTO, photo_result)

    payload = {
        "profile_ok": profile_ok,
        "first_name": names.get("first_name"),
        "last_name": names.get("last_name"),
        "bio": names.get("bio"),
        "username": chosen_username,
        "photo": photo_result,
    }
    await mark_done(repos, payload)
    return payload
