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
        max_tokens=4096,
        response_format={"type": "json_object"},
    )


async def _critique(persona_obj: dict) -> dict:
    """Second-pass critic with a fix patch."""
    sys = render("persona_critic.j2")
    usr = "Persona JSON:\n" + orjson.dumps(persona_obj, option=orjson.OPT_INDENT_2).decode()
    return await think_json(
        [{"role": "system", "content": sys}, {"role": "user", "content": usr}],
        temperature=0.2,
        max_tokens=2048,
        response_format={"type": "json_object"},
    )


def _post_normalize(obj: dict, seed: int) -> dict:
    """Force schema_version, seed, normalized traits and derived labels."""
    obj["schema_version"] = 1
    obj["seed"] = seed
    obj["traits"] = normalize_traits(obj.get("traits") or {})
    obj["derived"] = derive_all(obj["traits"])
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
