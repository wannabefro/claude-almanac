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


def test_default_code_index_has_safe_off_by_default():
    c = config.default_config()
    assert c.code_index.daily_refresh is False
    assert c.code_index.refresh_hour == 4
    assert c.auto_upgrade is False


def test_load_code_index_refresh_flag(tmp_path, monkeypatch):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "code_index:\n"
        "  daily_refresh: true\n"
        "  refresh_hour: 5\n"
        "auto_upgrade: true\n"
    )
    monkeypatch.setenv("CLAUDE_ALMANAC_CONFIG_DIR", str(tmp_path))
    c = config.load()
    assert c.code_index.daily_refresh is True
    assert c.code_index.refresh_hour == 5
    assert c.auto_upgrade is True


def test_materialize_missing_fields_writes_defaults(tmp_path, monkeypatch):
    """A config.yaml missing new fields should be rewritten so
    `claude-almanac setup` can bring users forward without manual editing."""
    monkeypatch.setenv("CLAUDE_ALMANAC_CONFIG_DIR", str(tmp_path))
    cfg = tmp_path / "config.yaml"
    # A minimal, old-style config written before `daily_refresh` existed.
    cfg.write_text("embedder:\n  provider: ollama\n  model: bge-m3\n")
    assert config.materialize_missing_fields() is True
    text = cfg.read_text()
    # New default fields should be materialized after the rewrite.
    assert "daily_refresh" in text
    assert "auto_upgrade" in text


def test_materialize_missing_fields_noop_when_canonical(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_ALMANAC_CONFIG_DIR", str(tmp_path))
    c = config.default_config()
    config.save(c)
    # Saving writes the canonical form, so a follow-up materialize is a no-op.
    assert config.materialize_missing_fields() is False
