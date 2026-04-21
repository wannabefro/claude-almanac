"""Tests for v0.3.11 config surface: retrieval.code.hybrid_enabled."""
from __future__ import annotations

from claude_almanac.core import config as _cfg


def test_default_config_enables_hybrid_code_retrieval():
    c = _cfg.default_config()
    assert c.retrieval.code.hybrid_enabled is True
    assert c.retrieval.code.keyword_k == 10
    assert c.retrieval.code.rrf_k == 60


def test_pre_0_3_11_config_still_loads_with_code_defaults():
    """A config YAML with no retrieval.code block must still parse and expose
    hybrid_enabled=True."""
    yaml_text = """
embedder:
  provider: ollama
  model: qwen3-embedding:0.6b
retrieval:
  top_k: 5
  decay:
    enabled: true
"""
    c = _cfg.load_config_from_text(yaml_text)
    assert c.retrieval.code.hybrid_enabled is True


def test_hybrid_disabled_via_yaml_override():
    yaml_text = """
retrieval:
  code:
    hybrid_enabled: false
"""
    c = _cfg.load_config_from_text(yaml_text)
    assert c.retrieval.code.hybrid_enabled is False


def test_code_retrieval_constants_overridable():
    yaml_text = """
retrieval:
  code:
    hybrid_enabled: true
    keyword_k: 20
    rrf_k: 30
"""
    c = _cfg.load_config_from_text(yaml_text)
    assert c.retrieval.code.keyword_k == 20
    assert c.retrieval.code.rrf_k == 30
