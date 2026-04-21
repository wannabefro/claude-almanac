"""Code-subsystem scoring profile (v0.4).

Freezes the v0.3.14 retrieval-quality rules: structural-symbol penalty
(0.4x), single-line-variable penalty (0.6x), pre-fusion vector
demotion of un-named structural symbols.
"""
from __future__ import annotations

from claude_almanac.contentindex.scoring import ScoringProfile

CODE_PROFILE = ScoringProfile(
    structural_names=frozenset(
        {"logger", "__init__", "__all__", "__main__", "dispatch", "main"}
    ),
    structural_name_penalty=0.4,
    single_line_var_penalty=0.6,
    demote_structural_in_vector=True,
)
