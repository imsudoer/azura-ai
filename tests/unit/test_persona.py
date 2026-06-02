"""Persona schema, derived labels, immutability lock."""
from __future__ import annotations

import pytest

from azura.personality.loader import ensure_immutable, save_persona, verify_lock
from azura.personality.traits import derive_all, normalize_traits
from tests.factories import make_persona


def test_traits_normalized_to_unit():
    t = normalize_traits({"empathy": 5.0, "narcissism": -0.5, "sarcasm": 0.7})
    assert t["empathy"] == 1.0
    assert t["narcissism"] == 0.0
    assert 0 <= t["sarcasm"] <= 1


def test_derived_labels_present():
    t = normalize_traits({})
    d = derive_all(t)
    assert "attachment_style" in d
    assert "humor_style" in d
    assert "conflict_style" in d


def test_high_empathy_secure_attachment():
    t = normalize_traits({"agreeableness": 0.8, "neuroticism": 0.2, "extraversion": 0.6})
    d = derive_all(t)
    assert d["attachment_style"] == "secure"


def test_high_aggression_competes():
    t = normalize_traits({"dominance": 0.9, "agreeableness": 0.2, "patience": 0.3})
    d = derive_all(t)
    assert d["conflict_style"] == "compete"


def test_persona_save_load_lock(tmp_path):
    p = make_persona()
    pp = tmp_path / "persona.json"
    lp = tmp_path / "persona.lock"
    save_persona(p, pp, lp)
    loaded = ensure_immutable(pp, lp)
    assert loaded.identity.name == p.identity.name


def test_lock_detects_byte_tamper(tmp_path):
    p = make_persona()
    pp = tmp_path / "p.json"
    lp = tmp_path / "p.lock"
    save_persona(p, pp, lp)
    pp.write_bytes(pp.read_bytes() + b" ")
    with pytest.raises(RuntimeError, match="modified"):
        ensure_immutable(pp, lp)


def test_lock_detects_canonical_change(tmp_path):
    p = make_persona()
    pp = tmp_path / "p.json"
    lp = tmp_path / "p.lock"
    save_persona(p, pp, lp)
    data = pp.read_text(encoding="utf-8").replace("Mira", "Vera")
    pp.write_text(data, encoding="utf-8")
    with pytest.raises(RuntimeError):
        ensure_immutable(pp, lp)


def test_persona_speech_alias_roundtrip():
    p = make_persona(speech={"register": "slangy"})
    dump = p.model_dump(by_alias=True)
    assert dump["speech"]["register"] == "slangy"
