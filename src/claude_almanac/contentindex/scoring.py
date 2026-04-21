"""Per-kind scoring rules for the content-index engine (v0.4).

Pulled out of keyword.py + search.py during the v0.4 refactor so each
subsystem (codeindex, documents) supplies its own scoring rules instead
of the engine hardcoding code-specific assumptions. See
docs/superpowers/specs/2026-04-21-v0.4-documents-and-engine-refactor-design.md.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ScoringProfile:
    """Per-kind scoring rules for the keyword channel + vector demotion.

    Every rule defaults to a no-op so kinds without special cases can
    pass ``ScoringProfile()`` and inherit plain LIKE-count scoring.

    Attributes:
      structural_names: lowercase symbol names that take the structural
        penalty when no query token matches the symbol_name.
      structural_name_penalty: multiplier applied to such rows' keyword
        score. 1.0 disables.
      single_line_var_penalty: multiplier for single-line variable rows
        when no query token matches the symbol_name. 1.0 disables.
      demote_structural_in_vector: if True, vector-channel hits matching
        ``structural_names`` with no name-token match are moved to the end
        of the pre-fusion list so their RRF contribution drops.
      min_confidence_distance: per-kind low-confidence cutoff override.
        None defers to the embedder profile's default.
    """
    structural_names: frozenset[str] = frozenset()
    structural_name_penalty: float = 1.0
    single_line_var_penalty: float = 1.0
    demote_structural_in_vector: bool = False
    min_confidence_distance: float | None = None
