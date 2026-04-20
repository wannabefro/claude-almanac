import pytest

from claude_almanac.core import archive


def test_init_creates_schema(tmp_path):
    db = tmp_path / "a.db"
    archive.init(db, embedder_name="ollama", model="bge-m3", dim=4, distance="l2")
    meta = archive.get_meta(db)
    assert meta["embedder"] == "ollama"
    assert meta["model"] == "bge-m3"
    assert meta["dim"] == 4
    assert meta["distance"] == "l2"


def test_mismatched_embedder_refuses(tmp_path):
    db = tmp_path / "a.db"
    archive.init(db, embedder_name="ollama", model="bge-m3", dim=4, distance="l2")
    with pytest.raises(archive.EmbedderMismatch):
        archive.assert_compatible(db, embedder_name="openai", model="any", dim=1536)


def test_insert_and_search_roundtrip(tmp_path):
    db = tmp_path / "a.db"
    archive.init(db, embedder_name="ollama", model="bge-m3", dim=2, distance="l2")
    archive.insert_entry(
        db,
        text="hello world",
        kind="reference",
        source="test",
        pinned=True,
        embedding=[1.0, 0.0],
    )
    archive.insert_entry(
        db,
        text="goodbye",
        kind="reference",
        source="test",
        pinned=False,
        embedding=[0.0, 1.0],
    )
    hits = archive.search(db, query_embedding=[1.0, 0.0], top_k=1)
    assert len(hits) == 1
    assert hits[0].text == "hello world"
    assert hits[0].distance < 0.1


def test_nearest_source_prefix_filter(tmp_path):
    db = tmp_path / "a.db"
    archive.init(db, embedder_name="ollama", model="bge-m3", dim=2, distance="l2")
    archive.insert_entry(
        db, text="a", kind="note", source="md:foo.md",
        pinned=True, embedding=[1.0, 0.0],
    )
    archive.insert_entry(
        db, text="b", kind="note", source="turn",
        pinned=False, embedding=[1.0, 0.0],
    )
    hit = archive.nearest(db, query_embedding=[1.0, 0.0], source_prefix="md:")
    assert hit.source == "md:foo.md"


def test_mismatched_model_refuses(tmp_path):
    db = tmp_path / "a.db"
    archive.init(db, embedder_name="ollama", model="bge-m3", dim=4, distance="l2")
    with pytest.raises(archive.EmbedderMismatch):
        archive.init(db, embedder_name="ollama", model="other-model", dim=4, distance="l2")



def test_set_pinned_flips_flag(tmp_path):
    db = tmp_path / "a.db"
    archive.init(db, embedder_name="ollama", model="bge-m3", dim=2, distance="l2")
    rowid = archive.insert_entry(
        db, text="t", kind="note", source="md:foo.md",
        pinned=False, embedding=[0.0, 1.0],
    )
    archive.set_pinned(db, row_id=rowid, pinned=True)
    meta = [r for r in archive.search(
        db, query_embedding=[0.0, 1.0], top_k=5)]
    assert meta[0].pinned is True
    archive.set_pinned(db, row_id=rowid, pinned=False)
    meta = [r for r in archive.search(
        db, query_embedding=[0.0, 1.0], top_k=5)]
    assert meta[0].pinned is False


def test_set_pinned_by_slug_matches_source_column(tmp_path):
    db = tmp_path / "a.db"
    archive.init(db, embedder_name="ollama", model="bge-m3", dim=2, distance="l2")
    archive.insert_entry(
        db, text="t", kind="note", source="md:project_foo.md",
        pinned=False, embedding=[0.0, 1.0],
    )
    count = archive.set_pinned_by_slug(db, slug="project_foo.md", pinned=True)
    assert count == 1
    hits = archive.search(db, query_embedding=[0.0, 1.0], top_k=5)
    assert hits[0].pinned is True


def test_delete_by_slug_removes_entries_and_vectors(tmp_path):
    db = tmp_path / "a.db"
    archive.init(db, embedder_name="ollama", model="bge-m3", dim=2, distance="l2")
    archive.insert_entry(
        db, text="keep", kind="note", source="md:keep.md",
        pinned=False, embedding=[1.0, 0.0],
    )
    archive.insert_entry(
        db, text="drop", kind="note", source="md:drop.md",
        pinned=False, embedding=[0.0, 1.0],
    )
    removed = archive.delete_by_slug(db, slug="drop.md")
    assert removed == 1
    hits = archive.search(db, query_embedding=[0.0, 1.0], top_k=5)
    assert [h.source for h in hits] == ["md:keep.md"]


def test_hit_carries_usage_fields(tmp_path):
    db = tmp_path / "a.db"
    archive.init(db, embedder_name="ollama", model="bge-m3", dim=2, distance="l2")
    entry_id = archive.insert_entry(
        db, text="hello", kind="reference", source="test",
        pinned=False, embedding=[1.0, 0.0],
    )
    # Fresh-insert defaults
    hits = archive.search(db, query_embedding=[1.0, 0.0], top_k=1)
    assert hits[0].use_count == 0
    assert hits[0].last_used_at is None

    # Round-trip: write non-default values, confirm search returns them
    import sqlite3
    conn = sqlite3.connect(str(db))
    conn.execute(
        "UPDATE entries SET last_used_at = 9999, use_count = 7 WHERE id = ?",
        (entry_id,),
    )
    conn.commit()
    conn.close()
    hits = archive.search(db, query_embedding=[1.0, 0.0], top_k=1)
    assert hits[0].use_count == 7
    assert hits[0].last_used_at == 9999


def test_reinforce_bumps_use_count_and_last_used_at(tmp_path):
    import time
    db = tmp_path / "a.db"
    archive.init(db, embedder_name="ollama", model="bge-m3", dim=2, distance="l2")
    id1 = archive.insert_entry(
        db, text="a", kind="note", source="t", pinned=False, embedding=[1.0, 0.0],
    )
    archive.insert_entry(
        db, text="b", kind="note", source="t", pinned=False, embedding=[0.0, 1.0],
    )
    before = int(time.time())
    archive.reinforce(db, ids=[id1])
    after = int(time.time())

    hits1 = archive.search(db, query_embedding=[1.0, 0.0], top_k=1)
    hits2 = archive.search(db, query_embedding=[0.0, 1.0], top_k=1)
    assert hits1[0].use_count == 1
    assert hits1[0].last_used_at is not None
    assert before <= hits1[0].last_used_at <= after
    # second entry untouched
    assert hits2[0].use_count == 0
    assert hits2[0].last_used_at is None


def test_reinforce_empty_list_is_noop(tmp_path):
    db = tmp_path / "a.db"
    archive.init(db, embedder_name="ollama", model="bge-m3", dim=2, distance="l2")
    archive.reinforce(db, ids=[])  # must not raise


def test_reinforce_multiple_ids(tmp_path):
    db = tmp_path / "a.db"
    archive.init(db, embedder_name="ollama", model="bge-m3", dim=2, distance="l2")
    id1 = archive.insert_entry(
        db, text="a", kind="note", source="t", pinned=False, embedding=[1.0, 0.0],
    )
    id2 = archive.insert_entry(
        db, text="b", kind="note", source="t", pinned=False, embedding=[0.0, 1.0],
    )
    count = archive.reinforce(db, ids=[id1, id2], now=5000)
    assert count == 2
    h1 = archive.search(db, query_embedding=[1.0, 0.0], top_k=1)[0]
    h2 = archive.search(db, query_embedding=[0.0, 1.0], top_k=1)[0]
    assert h1.use_count == 1
    assert h1.last_used_at == 5000
    assert h2.use_count == 1
    assert h2.last_used_at == 5000
