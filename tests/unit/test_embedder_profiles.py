from claude_almanac.embedders import profiles


def test_bge_m3_rank_band_is_in_rule_of_thumb_range() -> None:
    """rank_band should be 5–15% of bge-m3's ~1.4 L2 ceiling, i.e. [0.07, 0.21]."""
    p = profiles.get("ollama", "bge-m3")
    assert 0.07 <= p.rank_band <= 0.21


def test_bge_m3_rank_band_smaller_than_dedup_distance() -> None:
    """rank_band must not approach the dedup threshold or it breaks the
    semantic distinction (dedup = 'duplicate', band = 'tied for ranking')."""
    p = profiles.get("ollama", "bge-m3")
    assert p.rank_band < p.dedup_distance / 2


def test_cosine_profiles_rank_band_in_rule_of_thumb_range() -> None:
    """For cosine distance in [0, 2], rank_band should be 2.5–10% of range, i.e. [0.05, 0.2]
    (lower end of rule-of-thumb because cosine clusters are tighter than L2).
    """
    for provider, model in [
        ("openai", "text-embedding-3-small"),
        ("voyage", "voyage-3-large"),
    ]:
        p = profiles.get(provider, model)
        assert 0.03 <= p.rank_band <= 0.1, f"{provider}/{model} rank_band={p.rank_band}"


def test_cosine_profiles_rank_band_smaller_than_dedup_distance() -> None:
    for provider, model in [
        ("openai", "text-embedding-3-small"),
        ("voyage", "voyage-3-large"),
    ]:
        p = profiles.get(provider, model)
        assert p.rank_band < p.dedup_distance / 2, f"{provider}/{model}"
