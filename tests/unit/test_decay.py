"""Pure scoring function for temporal decay ranking."""
import math

from claude_almanac.core import decay


def test_fresh_memory_never_reinforced_scores_one():
    # use_count=0, age=0 → (0+1)^0.6 * e^0 = 1.0
    score = decay.decay_score(
        created_at=1000, last_used_at=None, use_count=0, now=1000,
        half_life_days=60, use_count_exponent=0.6,
    )
    assert math.isclose(score, 1.0, rel_tol=1e-6)


def test_half_life_halves_score():
    half_life_s = 60 * 86400
    score = decay.decay_score(
        created_at=0, last_used_at=None, use_count=0, now=half_life_s,
        half_life_days=60, use_count_exponent=0.6,
    )
    assert math.isclose(score, 0.5, rel_tol=1e-3)


def test_use_count_boosts_sublinearly():
    # (10+1)^0.6 ≈ 4.349
    score = decay.decay_score(
        created_at=1000, last_used_at=1000, use_count=10, now=1000,
        half_life_days=60, use_count_exponent=0.6,
    )
    assert math.isclose(score, 11 ** 0.6, rel_tol=1e-6)


def test_last_used_at_overrides_created_at():
    # created long ago but recently reinforced → score comes from last_used_at
    long_ago = 0
    recent = 30 * 86400  # 30 days after epoch
    now = 60 * 86400     # another 30 days later
    score = decay.decay_score(
        created_at=long_ago, last_used_at=recent, use_count=1, now=now,
        half_life_days=60, use_count_exponent=0.6,
    )
    # Δt should be 30 days, not 60
    expected = (2 ** 0.6) * math.exp(-math.log(2) / 60 * 30)
    assert math.isclose(score, expected, rel_tol=1e-3)


def test_monotone_decreasing_in_age():
    def s(age_s):
        return decay.decay_score(
            created_at=0, last_used_at=None, use_count=0, now=age_s,
            half_life_days=60, use_count_exponent=0.6,
        )
    assert s(0) > s(1) > s(86400) > s(86400 * 60)


def test_negative_dt_clamped():
    # Clock skew: now < last_used_at. Should not explode; score stays ≤ 1.0 for use_count=0.
    score = decay.decay_score(
        created_at=1000, last_used_at=2000, use_count=0, now=1000,
        half_life_days=60, use_count_exponent=0.6,
    )
    assert math.isclose(score, 1.0, rel_tol=1e-6)
