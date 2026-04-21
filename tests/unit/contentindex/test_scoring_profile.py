"""Locks the ScoringProfile contract (v0.4)."""
from __future__ import annotations

import pytest

from claude_almanac.contentindex.scoring import ScoringProfile


def test_default_profile_is_noop():
    p = ScoringProfile()
    assert p.structural_names == frozenset()
    assert p.structural_name_penalty == 1.0
    assert p.single_line_var_penalty == 1.0
    assert p.demote_structural_in_vector is False
    assert p.min_confidence_distance is None


def test_profile_is_frozen():
    import dataclasses
    p = ScoringProfile()
    with pytest.raises(dataclasses.FrozenInstanceError):
        p.structural_name_penalty = 0.5  # type: ignore[misc]


def test_code_profile_has_v0_3_14_rules():
    """Locks the v0.3.14 structural-penalty set and multipliers."""
    from claude_almanac.codeindex.scoring import CODE_PROFILE
    assert CODE_PROFILE.structural_names == frozenset(
        {"logger", "__init__", "__all__", "__main__", "dispatch", "main"}
    )
    assert CODE_PROFILE.structural_name_penalty == 0.4
    assert CODE_PROFILE.single_line_var_penalty == 0.6
    assert CODE_PROFILE.demote_structural_in_vector is True
