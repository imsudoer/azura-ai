"""LLM-driven persona generation: outline, validate, critic-loop, lock."""
from __future__ import annotations

import os
from typing import Any

import orjson

from azura.constants import PERSONALITY_TRAITS
from azura.llm.prompts import render
from azura.llm.router import think_json
from azura.personality.schema import Persona
from azura.personality.traits import derive_all, normalize_traits
from azura.utils.log import get_logger
from azura.utils.rng import Rng

log = get_logger("persona.gen")


def _seed_int() -> int:
    return int.from_bytes(os.urandom(8), "little")


def _hints_json(hints: dict[str, Any]) -> str:
    """Render hints as canonical JSON for the user prompt."""
    return orjson.dumps(hints, option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS).decode()


def _traits_list() -> str:
    return ", ".join(PERSONALITY_TRAITS)


def _deep_merge(base: dict, patch: dict) -> dict:
    """Recursively merge patch into base, scalar overrides scalar, lists replace lists."""
    out = dict(base)
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


async def _draft(hints: dict, *, temperature: float) -> dict:
    """First-pass persona draft via the thinking model."""
    sys = render("persona_outline.j2")
    usr = render("persona_user.j2", hints_json=_hints_json(hints), traits_list=_traits_list())
    return await think_json(
        [{"role": "system", "content": sys}, {"role": "user", "content": usr}],
        temperature=temperature,
        max_tokens=8192,
    )


async def _critique(persona_obj: dict) -> dict:
    """Second-pass critic with a fix patch."""
    sys = render("persona_critic.j2")
    usr = "Persona JSON:\n" + orjson.dumps(persona_obj, option=orjson.OPT_INDENT_2).decode()
    return await think_json(
        [{"role": "system", "content": sys}, {"role": "user", "content": usr}],
        temperature=0.2,
        max_tokens=4096,
    )


_SPEECH_REGISTER = ("formal", "neutral", "casual", "slangy")
_FREQ_VALUES = ("never", "rare", "moderate", "often")
_PUNCT_VALUES = ("strict", "loose", "messy")
_REPLY_SPEED = ("instant", "fast", "medium", "slow", "lazy")


def _coerce_enum(value, allowed: tuple[str, ...], default: str) -> str:
    """Best-effort: pick an exact match, else substring match, else default."""
    if isinstance(value, bool):
        return "moderate" if (value and "moderate" in allowed) else ("rare" if "rare" in allowed else default)
    if not isinstance(value, str):
        return default
    s = value.strip().lower()
    if s in allowed:
        return s
    for opt in allowed:
        if opt in s:
            return opt
    return default


def _coerce_dict_list(value, key_name: str = "name") -> list[dict]:
    """Wrap strings/objects into a list[dict] form."""
    if not isinstance(value, list):
        return []
    out: list[dict] = []
    for item in value:
        if isinstance(item, dict):
            out.append(item)
        elif isinstance(item, str):
            out.append({key_name: item})
    return out


def _coerce_str_list(value, *, key_for_dict: str = "name") -> list[str]:
    """Flatten a list[str|dict] into list[str]."""
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        if isinstance(item, str):
            out.append(item)
        elif isinstance(item, dict):
            parts = []
            for k in (key_for_dict, "title", "species", "name"):
                v = item.get(k)
                if isinstance(v, str):
                    parts.append(v)
                    break
            extra = []
            for k, v in item.items():
                if k in (key_for_dict, "title", "species", "name"):
                    continue
                if isinstance(v, str):
                    extra.append(f"{k}={v}")
            joined = (": ".join(parts) if parts else "") + (" (" + ", ".join(extra) + ")" if extra else "")
            if joined.strip():
                out.append(joined.strip())
    return out


def _post_normalize(obj: dict, seed: int) -> dict:
    """Force schema_version, seed, normalized traits, derived labels, and shape coercions."""
    obj["schema_version"] = 1
    obj["seed"] = seed
    obj["traits"] = normalize_traits(obj.get("traits") or {})
    obj["derived"] = derive_all(obj["traits"])

    sp = obj.get("speech") or {}
    if isinstance(sp, dict):
        if "register" in sp:
            sp["register"] = _coerce_enum(sp.get("register"), _SPEECH_REGISTER, "casual")
        if "uses_emoji" in sp:
            sp["uses_emoji"] = _coerce_enum(sp.get("uses_emoji"), _FREQ_VALUES, "rare")
        if "uses_caps" in sp:
            sp["uses_caps"] = _coerce_enum(sp.get("uses_caps"), _FREQ_VALUES, "rare")
        if "punctuation" in sp:
            sp["punctuation"] = _coerce_enum(sp.get("punctuation"), _PUNCT_VALUES, "loose")
        obj["speech"] = sp

    soc = obj.get("social") or {}
    if isinstance(soc, dict) and "reply_speed" in soc:
        soc["reply_speed"] = _coerce_enum(soc.get("reply_speed"), _REPLY_SPEED, "medium")
        obj["social"] = soc

    hh = obj.get("household") or {}
    if isinstance(hh, dict):
        hh["pets"] = _coerce_str_list(hh.get("pets"), key_for_dict="species")
        hh["lives_with"] = _coerce_str_list(hh.get("lives_with"))
        obj["household"] = hh

    sc = obj.get("social_circle") or {}
    if isinstance(sc, dict):
        for key in ("close_friends", "acquaintances", "rivals"):
            sc[key] = _coerce_dict_list(sc.get(key))
        obj["social_circle"] = sc

    if isinstance(obj.get("life_events"), list):
        cleaned = []
        for ev in obj["life_events"]:
            if isinstance(ev, dict) and ev.get("title") and ev.get("description"):
                ev.setdefault("when", "unspecified")
                cleaned.append(ev)
        obj["life_events"] = cleaned

    for k in ("values", "interests", "dislikes", "secrets", "habits"):
        if k in obj:
            obj[k] = _coerce_str_list(obj[k])

    return obj


async def generate(hints: dict[str, Any], *, critic_passes: int = 1) -> Persona:
    """Full generation cycle: draft -> validate -> critic loop -> validate."""
    seed = int(hints.get("seed") or _seed_int())
    rng = Rng(seed)
    hints = dict(hints)
    hints.setdefault("seed", seed)
    log.info("persona generation, seed={}", seed)

    obj = await _draft(hints, temperature=0.95 - 0.1 * rng.uniform(-0.5, 0.5))
    obj = _post_normalize(obj, seed)

    for i in range(max(0, critic_passes)):
        crit = await _critique(obj)
        if crit.get("ok"):
            log.info("critic pass {}: ok", i + 1)
            break
        issues = crit.get("issues") or []
        patch = crit.get("patch") or {}
        log.info("critic pass {}: {} issue(s), applying patch", i + 1, len(issues))
        obj = _deep_merge(obj, patch)
        obj = _post_normalize(obj, seed)

    return Persona.model_validate(obj)
