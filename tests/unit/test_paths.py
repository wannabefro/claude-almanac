import hashlib

from claude_almanac.core import paths


def test_data_dir_respects_env_override(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path))
    assert paths.data_dir() == tmp_path


def test_config_dir_respects_env_override(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_ALMANAC_CONFIG_DIR", str(tmp_path))
    assert paths.config_dir() == tmp_path


def test_global_dir_is_under_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path))
    assert paths.global_memory_dir() == tmp_path / "global"


def test_project_key_uses_git_common_dir(tmp_path, monkeypatch):
    # Simulate a git repo
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    monkeypatch.chdir(repo)
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path / "data"))

    key = paths.project_key()
    expected = "git-" + hashlib.sha256(str(repo.resolve()).encode()).hexdigest()[:16]
    assert key == expected


def test_project_key_falls_back_to_cwd_when_not_git(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path / "data"))

    key = paths.project_key()
    assert key.startswith("cwd-")


def test_project_memory_dir_joins_key(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    monkeypatch.chdir(repo)
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path / "data"))

    assert paths.project_memory_dir().parent.name == "projects"
