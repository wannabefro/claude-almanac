"""Tests for v0.3.2 config sections: rollup + retrieval.rollups + retrieval.edges."""


from claude_almanac.core.config import load_config_from_text


def test_v0_3_1_config_still_loads_with_defaults():
    """Config with no v0.3.2 keys must still parse and expose defaults."""
    text = "curator:\n  provider: ollama\n  model: gemma3:4b\n"
    cfg = load_config_from_text(text)
    assert cfg.retrieval.rollups.autoinject is False
    assert cfg.retrieval.edges.skip_superseded is True
    assert cfg.retrieval.edges.expand is False
    assert cfg.rollup.enabled is True
    assert cfg.rollup.idle_threshold_minutes == 45


def test_v0_3_2_overrides_parse():
    """All v0.3.2 settings parse correctly."""
    text = """
retrieval:
  rollups:
    autoinject: true
    topk: 2
  edges:
    expand: true
    expand_bonus: 0.5
rollup:
  idle_threshold_minutes: 30
  min_turns: 5
"""
    cfg = load_config_from_text(text)
    assert cfg.retrieval.rollups.autoinject is True
    assert cfg.retrieval.rollups.topk == 2
    assert cfg.retrieval.edges.expand is True
    assert cfg.retrieval.edges.expand_bonus == 0.5
    assert cfg.rollup.idle_threshold_minutes == 30
    assert cfg.rollup.min_turns == 5


def test_rollup_provider_default_is_null_without_api_key(monkeypatch):
    """Without ANTHROPIC_API_KEY, rollup.provider defaults to None."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    cfg = load_config_from_text("")
    assert cfg.rollup.provider is None


def test_rollup_provider_auto_anthropic_when_api_key_set(monkeypatch):
    """With ANTHROPIC_API_KEY set, rollup.provider auto-defaults to anthropic_sdk."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    cfg = load_config_from_text("")
    assert cfg.rollup.provider == "anthropic_sdk"


def test_rollup_provider_explicit_override_respected(monkeypatch):
    """Explicit rollup.provider in config overrides env-var auto-default."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    cfg = load_config_from_text("rollup:\n  provider: ollama\n")
    assert cfg.rollup.provider == "ollama"


def test_rollup_all_defaults_present():
    """All rollup fields have sensible defaults."""
    cfg = load_config_from_text("")
    assert cfg.rollup.enabled is True
    assert cfg.rollup.idle_threshold_minutes == 45
    assert cfg.rollup.max_transcript_tokens == 32000
    assert cfg.rollup.min_turns == 3
    assert cfg.rollup.provider is None


def test_retrieval_rollups_all_defaults_present():
    """All retrieval.rollups fields have sensible defaults."""
    cfg = load_config_from_text("")
    assert cfg.retrieval.rollups.autoinject is False
    assert cfg.retrieval.rollups.topk == 1
    assert cfg.retrieval.rollups.distance_cutoff == 0.4
    assert cfg.retrieval.rollups.half_life_days == 30
    assert cfg.retrieval.rollups.use_count_exponent == 0.5


def test_retrieval_edges_all_defaults_present():
    """All retrieval.edges fields have sensible defaults."""
    cfg = load_config_from_text("")
    assert cfg.retrieval.edges.expand is False
    assert cfg.retrieval.edges.expand_hops == 1
    assert cfg.retrieval.edges.expand_bonus == 0.25
    assert cfg.retrieval.edges.skip_superseded is True


def test_partial_rollup_config_preserves_unspecified_defaults():
    """Partial rollup config doesn't clobber unspecified fields."""
    text = "rollup:\n  enabled: false\n"
    cfg = load_config_from_text(text)
    assert cfg.rollup.enabled is False
    assert cfg.rollup.idle_threshold_minutes == 45  # default
    assert cfg.rollup.max_transcript_tokens == 32000  # default
    assert cfg.rollup.min_turns == 3  # default


def test_partial_rollups_retrieval_config_preserves_unspecified_defaults():
    """Partial retrieval.rollups config preserves other defaults."""
    text = "retrieval:\n  rollups:\n    autoinject: true\n"
    cfg = load_config_from_text(text)
    assert cfg.retrieval.rollups.autoinject is True
    assert cfg.retrieval.rollups.topk == 1  # default
    assert cfg.retrieval.rollups.distance_cutoff == 0.4  # default
    assert cfg.retrieval.rollups.half_life_days == 30  # default
    assert cfg.retrieval.rollups.use_count_exponent == 0.5  # default


def test_partial_edges_retrieval_config_preserves_unspecified_defaults():
    """Partial retrieval.edges config preserves other defaults."""
    text = "retrieval:\n  edges:\n    expand: true\n"
    cfg = load_config_from_text(text)
    assert cfg.retrieval.edges.expand is True
    assert cfg.retrieval.edges.expand_hops == 1  # default
    assert cfg.retrieval.edges.expand_bonus == 0.25  # default
    assert cfg.retrieval.edges.skip_superseded is True  # default
