import pytest
from claude_almanac.core import config


def test_default_config_has_ollama():
    c = config.default_config()
    assert c.embedder.provider == "ollama"
    assert c.embedder.model == "bge-m3"
    assert c.digest.enabled is False


def test_load_config_reads_yaml(tmp_path, monkeypatch):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "embedder:\n"
        "  provider: openai\n"
        "  model: text-embedding-3-small\n"
        "digest:\n"
        "  enabled: true\n"
        "  hour: 8\n"
    )
    monkeypatch.setenv("CLAUDE_ALMANAC_CONFIG_DIR", str(tmp_path))
    c = config.load()
    assert c.embedder.provider == "openai"
    assert c.digest.enabled is True
    assert c.digest.hour == 8


def test_load_config_returns_defaults_when_absent(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_ALMANAC_CONFIG_DIR", str(tmp_path))
    c = config.load()
    assert c.embedder.provider == "ollama"


def test_save_config_writes_yaml(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_ALMANAC_CONFIG_DIR", str(tmp_path))
    c = config.default_config()
    config.save(c)
    assert (tmp_path / "config.yaml").exists()
    loaded = config.load()
    assert loaded == c
