from unittest.mock import MagicMock

import pytest

from claude_almanac.core import archive
from claude_almanac.digest import activity_db


def _fake_embedder():
    emb = MagicMock()
    emb.name = "ollama"
    emb.dim = 4
    emb.distance = "l2"
    emb.embed.return_value = [[0.1, 0.2, 0.3, 0.4]]
    return emb


def test_init_creates_tables(tmp_path):
    emb = _fake_embedder()
    db = tmp_path / "activity.db"
    activity_db.init_db(db, embedder=emb, model="bge-m3")
    meta = archive.get_meta(db)
    assert meta["embedder"] == "ollama"
    assert meta["dim"] == 4


def test_insert_commit_dedupes_on_source(tmp_path):
    emb = _fake_embedder()
    db = tmp_path / "activity.db"
    activity_db.init_db(db, embedder=emb, model="bge-m3")
    rec = activity_db.CommitRecord(
        repo="r", sha="abc123", author="t", subject="feat: x",
        body="", stat_files=1, stat_insertions=2, stat_deletions=0,
        diff_snippet="diff --git ...", committed_at="2026-04-19T10:00:00Z",
    )
    assert activity_db.insert_commit(db, rec, embedder=emb, model="bge-m3") is True
    assert activity_db.insert_commit(db, rec, embedder=emb, model="bge-m3") is False


def test_assert_compatible_raises_on_drift(tmp_path):
    emb = _fake_embedder()
    db = tmp_path / "activity.db"
    activity_db.init_db(db, embedder=emb, model="bge-m3")
    wrong = _fake_embedder()
    wrong.name = "openai"
    wrong.dim = 1536
    with pytest.raises(archive.EmbedderMismatch):
        activity_db.init_db(db, embedder=wrong, model="text-embedding-3-small")
