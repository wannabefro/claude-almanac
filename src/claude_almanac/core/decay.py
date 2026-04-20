"""Temporal decay scoring for archive ranking and pruning.

Formula: score = (use_count + 1)^β · exp(-λ · Δt)
  where λ = ln(2) / (half_life_days · 86400)
  and Δt = now - (last_used_at or created_at), clamped to [0, ∞).

The `+1` smoothing on use_count prevents fresh (never-reinforced) memories
from collapsing to score = 0.
"""
from __future__ import annotations

import math


def decay_score(
    created_at: int,
    last_used_at: int | None,
    use_count: int,
    now: int,
    *,
    half_life_days: int,
    use_count_exponent: float,
) -> float:
    """Usage-weighted recency score. Higher = more reinforced / more recent.

    Pinned memories should not call this; upstream code assigns score=1.0 to
    pinned hits directly.
    """
    reference_ts = last_used_at if last_used_at is not None else created_at
    dt_seconds = max(0, now - reference_ts)
    lam = math.log(2) / (half_life_days * 86400)
    use_factor = (use_count + 1) ** use_count_exponent
    return float(use_factor * math.exp(-lam * dt_seconds))
