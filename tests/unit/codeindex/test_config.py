from pathlib import Path

import pytest

from claude_almanac.codeindex import config as ci_config


def _write_yaml(root: Path, body: str) -> None:
    (root / ".claude").mkdir(parents=True, exist_ok=True)
    (root / ".claude" / "code-index.yaml").write_text(body)


def test_load_requires_default_branch(tmp_path):
    _write_yaml(tmp_path, "modules:\n  patterns: ['.']\n")
    with pytest.raises(ci_config.ConfigError):
        ci_config.load(str(tmp_path))


def test_load_rejects_both_from_and_patterns(tmp_path):
    _write_yaml(tmp_path,
                "default_branch: main\n"
                "modules:\n  from: auto\n  patterns: ['src/*']\n")
    with pytest.raises(ci_config.ConfigError):
        ci_config.load(str(tmp_path))


def test_load_patterns_mode(tmp_path):
    _write_yaml(tmp_path,
                "default_branch: main\n"
                "modules:\n  patterns: ['src']\n")
    cfg = ci_config.load(str(tmp_path))
    assert cfg.discovery_mode == "patterns"
    assert cfg.patterns == ["src"]
    assert cfg.send_code_to_llm is False  # spec default
    assert cfg.min_files_for_arch == 3


def test_load_auto_mode_defaults(tmp_path):
    _write_yaml(tmp_path,
                "default_branch: main\n"
                "modules:\n  from: auto\n")
    cfg = ci_config.load(str(tmp_path))
    assert cfg.discovery_mode == "auto"
    assert cfg.patterns == []


def test_discover_modules_patterns(tmp_path):
    _write_yaml(tmp_path,
                "default_branch: main\n"
                "modules:\n  patterns: ['pkg/*']\n")
    (tmp_path / "pkg" / "a").mkdir(parents=True)
    (tmp_path / "pkg" / "b").mkdir(parents=True)
    cfg = ci_config.load(str(tmp_path))
    mods = ci_config.discover_modules(cfg)
    assert [m.name for m in mods] == ["pkg/a", "pkg/b"]


def test_enumerate_files_excludes_binaries_and_large(tmp_path):
    mod_path = tmp_path / "m"
    mod_path.mkdir()
    (mod_path / "a.py").write_text("def f(): pass\n")
    (mod_path / "big.py").write_bytes(b"x" * (ci_config.MAX_FILE_BYTES + 1))
    (mod_path / "node_modules").mkdir()
    (mod_path / "node_modules" / "dep.js").write_text("x")
    mod = ci_config.Module(name="m", path=str(mod_path))
    files = ci_config.enumerate_files(mod, extra_excludes=[])
    names = [Path(f).name for f in files]
    assert "a.py" in names
    assert "big.py" not in names
    assert "dep.js" not in names


def test_is_sym_capable_majority_python():
    mix = {"py": 10, "sh": 3}
    assert ci_config.is_sym_capable(mix)


def test_is_sym_capable_majority_shell():
    mix = {"py": 3, "sh": 10}
    assert not ci_config.is_sym_capable(mix)


def test_docs_patterns_empty_list_raises(tmp_path):
    """Empty ``docs.patterns: []`` is ambiguous with "use defaults" and
    would silently disable ingest, so we raise explicitly."""
    _write_yaml(
        tmp_path,
        "default_branch: main\n"
        "modules:\n  patterns: ['src']\n"
        "docs:\n  patterns: []\n",
    )
    with pytest.raises(ci_config.ConfigError, match="patterns is empty"):
        ci_config.load(str(tmp_path))


def test_docs_missing_patterns_uses_defaults(tmp_path):
    """When ``docs.patterns`` is absent (not explicitly empty), the
    parser falls back to DEFAULT_DOC_PATTERNS — empty-list is the
    only case that raises."""
    _write_yaml(
        tmp_path,
        "default_branch: main\n"
        "modules:\n  patterns: ['src']\n"
        "docs:\n  enabled: true\n",
    )
    cfg = ci_config.load(str(tmp_path))
    assert cfg.docs.patterns == list(ci_config.DEFAULT_DOC_PATTERNS)
