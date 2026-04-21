from pathlib import Path
from unittest.mock import MagicMock, patch

from claude_almanac.codeindex import arch
from claude_almanac.codeindex import config as ci_config
from claude_almanac.contentindex import db as ci_db


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


def test_run_one_returns_false_on_embedder_failure(tmp_path):
    # Minimal direct run_one call: both flags True, _haiku returns a summary,
    # embedder.embed raises. Expect False + arch.embed_fail emitted.
    from claude_almanac.core import paths
    dbp = paths.project_memory_dir() / "code-index.db"
    dbp.parent.mkdir(parents=True, exist_ok=True)
    ci_db.init(str(dbp), dim=2)

    f1 = tmp_path / "main.py"
    f1.write_text("print('hi')\n")

    failing_embedder = MagicMock()
    failing_embedder.embed.side_effect = RuntimeError("boom")

    with patch("claude_almanac.codeindex.arch._haiku", return_value="A summary."):
        ok = arch.run_one(
            db_path=str(dbp), repo_root=str(tmp_path), module_name="m",
            files_=[str(f1)], language_mix={"py": 1}, commit_sha="sha1",
            embedder=failing_embedder,
            send_code_to_llm=True, global_send_code_to_llm=True,
        )
    assert ok is False
    log_text = (paths.logs_dir() / "code-index.log").read_text()
    assert "arch.embed_fail" in log_text


def test_run_one_refuses_when_flags_disabled(tmp_path):
    # Call run_one directly with repo send_code_to_llm=False: should return
    # False without touching _haiku or embedder, and log arch.refused.
    from claude_almanac.core import paths

    f1 = tmp_path / "main.py"
    f1.write_text("print('hi')\n")

    embedder = MagicMock()
    haiku_mock = MagicMock()
    with patch("claude_almanac.codeindex.arch._haiku", haiku_mock):
        ok = arch.run_one(
            db_path="/nonexistent", repo_root=str(tmp_path), module_name="m",
            files_=[str(f1)], language_mix={"py": 1}, commit_sha="sha1",
            embedder=embedder,
            send_code_to_llm=False, global_send_code_to_llm=True,
        )
    assert ok is False
    haiku_mock.assert_not_called()
    embedder.embed.assert_not_called()
    log_text = (paths.logs_dir() / "code-index.log").read_text()
    assert "arch.refused" in log_text


def test_arch_refuses_when_both_flags_false(tmp_path, capsys):
    # Both repo-local and global flags off: main() refuses (pre-existing
    # early-exit) and no LLM/embedder work happens.
    _make_cfg(tmp_path, send_flag=False)
    haiku_mock = MagicMock()
    embedder_factory = MagicMock()
    with patch("claude_almanac.codeindex.arch._haiku", haiku_mock), \
         patch("claude_almanac.codeindex.arch._make_embedder", embedder_factory):
        rc = arch.main(str(tmp_path), global_send_code_to_llm=False)
    assert rc == 0
    out = capsys.readouterr().out
    assert "send_code_to_llm" in out
    haiku_mock.assert_not_called()
    embedder_factory.assert_not_called()


def test_select_files_prioritises_entrypoints_over_large_non_entrypoints(tmp_path):
    # Create repo files: a big non-entrypoint + a small main.py
    main_py = tmp_path / "main.py"
    main_py.write_text("print('hi')\n")  # tiny
    heavy = tmp_path / "heavy_logic.py"
    heavy.write_text("x = 1\n" * 1000)  # large
    files = [str(main_py), str(heavy)]
    ordered = arch.select_files(files, cap=10)
    # main.py must come FIRST even though it's tiny
    assert Path(ordered[0]).name == "main.py"
    assert Path(ordered[1]).name == "heavy_logic.py"
