from claude_almanac.embedders import profiles


def test_bge_m3_has_rank_band():
    p = profiles.get("ollama", "bge-m3")
    assert p.rank_band > 0  # band is positive so it ever kicks in
    assert p.rank_band <= 0.5  # not absurdly large vs bge-m3's ~1.4 ceiling


def test_cosine_profiles_have_rank_band():
    for provider, model in [
        ("openai", "text-embedding-3-small"),
        ("voyage", "voyage-3-large"),
    ]:
        p = profiles.get(provider, model)
        assert p.rank_band > 0
        assert p.rank_band <= 0.2
