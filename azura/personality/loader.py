"""Load, save and lock the persona JSON with hash-based immutability checks."""
from __future__ import annotations

import hashlib
from pathlib import Path

import orjson

from azura.personality.schema import Persona
from azura.personality.traits import derive_all, normalize_traits


def _canonical(data: dict) -> bytes:
    return orjson.dumps(data, option=orjson.OPT_SORT_KEYS)


def _dump(p: Persona) -> dict:
    """Canonical dict form using JSON aliases."""
    return p.model_dump(mode="json", by_alias=True)


def _file_hash(path: Path) -> str:
    """Sha256 of the raw file bytes (detects any external edit, even whitespace)."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def persona_hash(p: Persona) -> str:
    """Stable sha256 of the canonical persona representation (alias dump, sorted keys)."""
    return hashlib.sha256(_canonical(_dump(p))).hexdigest()


def save_persona(p: Persona, path: Path, lock_path: Path) -> str:
    """Persist persona JSON and write a sibling lock file holding canonical+file hashes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    p.traits = normalize_traits(p.traits)
    p.derived = derive_all(p.traits)
    raw = orjson.dumps(_dump(p), option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS)
    path.write_bytes(raw)
    canon = persona_hash(p)
    fileh = _file_hash(path)
    lock_path.write_text(f"{canon}\n{fileh}\n", encoding="utf-8")
    return canon


def load_persona(path: Path) -> Persona:
    """Load persona JSON from disk."""
    return Persona.model_validate_json(path.read_bytes())


def verify_lock(path: Path, lock_path: Path) -> tuple[bool, str, str]:
    """Return (ok, expected_hash, actual_hash). Checks file bytes when both hashes recorded."""
    if not lock_path.exists():
        p = load_persona(path)
        return True, "", persona_hash(p)
    parts = lock_path.read_text(encoding="utf-8").splitlines()
    expected_canon = parts[0].strip() if parts else ""
    expected_file = parts[1].strip() if len(parts) > 1 else ""
    actual_file = _file_hash(path)
    if expected_file and expected_file != actual_file:
        return False, expected_file, actual_file
    p = load_persona(path)
    actual_canon = persona_hash(p)
    return expected_canon == actual_canon, expected_canon, actual_canon


def ensure_immutable(path: Path, lock_path: Path) -> Persona:
    """Load persona and raise if its hash does not match the lock."""
    ok, expected, actual = verify_lock(path, lock_path)
    if not ok:
        raise RuntimeError(
            f"persona file modified after generation (expected {expected[:8]}.., got {actual[:8]}..); "
            "regenerate via init_personality"
        )
    return load_persona(path)
