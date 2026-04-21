import pytest

from claude_almanac.contentindex import db


def _init(tmp_path, dim=2):
    path = tmp_path / "content-index.db"
    db.init(str(path), dim=dim)
    return str(path)


def test_init_creates_tables(tmp_path):
    p = _init(tmp_path)
    assert db.last_sha(p) is None


def test_upsert_sym_roundtrip(tmp_path):
    p = _init(tmp_path)
    db.upsert(
        p, kind="sym", text="def foo(): ...", file_path="src/a.py",
        symbol_name="foo", module="src", line_start=1, line_end=1,
        commit_sha="sha1", embedding=[1.0, 0.0],
    )
    hit = db.nearest(p, embedding=[1.0, 0.0])
    assert hit["kind"] == "sym"
    assert hit["symbol_name"] == "foo"


def test_upsert_sym_is_idempotent_by_symbol_key(tmp_path):
    p = _init(tmp_path)
    db.upsert(p, kind="sym", text="v1", file_path="src/a.py",
              symbol_name="foo", module="src",
              line_start=1, line_end=1, commit_sha="sha1",
              embedding=[1.0, 0.0])
    db.upsert(p, kind="sym", text="v2", file_path="src/a.py",
              symbol_name="foo", module="src",
              line_start=1, line_end=2, commit_sha="sha2",
              embedding=[1.0, 0.0])
    results = db.search(p, embedding=[1.0, 0.0], k=5, kind="sym")
    assert len(results) == 1
    assert results[0]["text"] == "v2"


def test_arch_upsert_is_keyed_by_module(tmp_path):
    p = _init(tmp_path)
    db.upsert(p, kind="arch", text="old summary", file_path=None,
              symbol_name=None, module="src",
              line_start=None, line_end=None, commit_sha="sha1",
              embedding=[1.0, 0.0])
    db.upsert(p, kind="arch", text="new summary", file_path=None,
              symbol_name=None, module="src",
              line_start=None, line_end=None, commit_sha="sha2",
              embedding=[1.0, 0.0])
    results = db.search(p, embedding=[1.0, 0.0], k=5, kind="arch")
    assert len(results) == 1
    assert results[0]["text"] == "new summary"


def test_delete_by_file_removes_entries_and_vec(tmp_path):
    p = _init(tmp_path)
    db.upsert(p, kind="sym", text="a", file_path="src/a.py",
              symbol_name="f", module="src",
              line_start=1, line_end=1, commit_sha="sha1",
              embedding=[1.0, 0.0])
    removed = db.delete_by_file(p, "src/a.py")
    assert removed == 1
    assert db.search(p, embedding=[1.0, 0.0], k=5) == []


def test_dirty_cycle(tmp_path):
    p = _init(tmp_path)
    db.mark_dirty(p, module="src", sha="sha1")
    assert db.list_dirty(p) == [("src", "sha1")]
    db.clear_dirty(p, "src")
    assert db.list_dirty(p) == []


def test_last_sha_returns_latest(tmp_path):
    p = _init(tmp_path)
    db.upsert(p, kind="sym", text="x", file_path="src/a.py",
              symbol_name="f", module="src",
              line_start=1, line_end=1, commit_sha="sha1",
              embedding=[1.0, 0.0])
    assert db.last_sha(p) == "sha1"


def test_upsert_rejects_unknown_kind(tmp_path):
    p = _init(tmp_path)
    with pytest.raises(ValueError, match=r"must be 'sym'\|'doc'\|'arch'"):
        db.upsert(
            p,
            kind="function",  # wrong: should be 'sym'
            text="...",
            file_path="src/a.py",
            symbol_name="foo",
            module="src",
            line_start=1,
            line_end=1,
            commit_sha="sha1",
            embedding=[1.0, 0.0],
        )
