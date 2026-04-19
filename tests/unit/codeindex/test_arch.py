from unittest.mock import MagicMock, patch

from claude_almanac.codeindex import arch, config as ci_config, db as ci_db


def _make_cfg(root, send_flag):
    mod_path = root / "m"
    mod_path.mkdir(exist_ok=True)
    (mod_path / "main.py").write_text("print('hi')\n")
    (mod_path / "util.py").write_text("def util(): pass\n")
    (root / ".claude").mkdir(exist_ok=True)
    (root / ".claude" / "code-index.yaml").write_text(
        f"default_branch: main\n"
        f"send_code_to_llm: {'true' if send_flag else 'false'}\n"
        f"min_files_for_arch: 1\n"
        f"modules:\n  patterns: ['m']\n"
    )
    return ci_config.load(str(root))


def test_arch_refuses_when_repo_flag_false(tmp_path, capsys):
    _make_cfg(tmp_path, send_flag=False)
    rc = arch.main(str(tmp_path), global_send_code_to_llm=True)
    assert rc == 0
    out = capsys.readouterr().out
    assert "send_code_to_llm" in out


def test_arch_refuses_when_global_flag_false(tmp_path, capsys):
    _make_cfg(tmp_path, send_flag=True)
    rc = arch.main(str(tmp_path), global_send_code_to_llm=False)
    assert rc == 0
    out = capsys.readouterr().out
    assert "send_code_to_llm" in out


def test_arch_writes_summary_when_both_flags_true(tmp_path):
    _make_cfg(tmp_path, send_flag=True)
    # Pre-populate DB + mark module dirty
    from claude_almanac.core import paths
    ci_dbp = paths.project_memory_dir() / "code-index.db"
    ci_dbp.parent.mkdir(parents=True, exist_ok=True)
    ci_db.init(str(ci_dbp), dim=2)
    ci_db.mark_dirty(str(ci_dbp), module="m", sha="sha1")

    fake_embedder = MagicMock()
    fake_embedder.embed.side_effect = lambda texts: [[1.0, 0.0] for _ in texts]

    with patch("claude_almanac.codeindex.arch._haiku", return_value="A test summary."), \
         patch("claude_almanac.codeindex.arch._git_target_sha", return_value="sha2"), \
         patch("claude_almanac.codeindex.arch._make_embedder", return_value=fake_embedder):
        rc = arch.main(str(tmp_path), global_send_code_to_llm=True)
    assert rc == 0
    results = ci_db.search(str(ci_dbp), embedding=[1.0, 0.0], k=5, kind="arch")
    assert any(r["module"] == "m" for r in results)
