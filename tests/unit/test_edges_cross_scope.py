import sqlite3
from pathlib import Path

from claude_almanac.core import archive
from claude_almanac.edges.cross_scope import resolve_cross_scope_neighbors
from claude_almanac.edges.store import insert_edge

_DIM = 4
_EMBEDDING = [1.0, 0.0, 0.0, 0.0]


def _init_db(path: Path) -> sqlite3.Connection:
    """Create a properly initialised archive DB and return an open connection.

    Calls archive.init first (which creates meta + entries + entries_vec), then
    ensure_schema on the returned connection to add edges + rollups tables that
    are only created via the migration path.
    """
    from claude_almanac.core.archive import ensure_schema
    from claude_almanac.embedders.profiles import get

    archive.init(path, embedder_name="ollama", model="bge-m3", dim=_DIM, distance="l2")
    conn = sqlite3.connect(str(path))
    conn.enable_load_extension(True)
    import sqlite_vec
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    ensure_schema(conn, profile=get("ollama", "bge-m3"))
    return conn


def _insert(db: Path, *, text: str, kind: str = "user") -> int:
    return archive.insert_entry(
        db, text=text, kind=kind, source="test", pinned=False, embedding=_EMBEDDING
    )


def test_resolves_global_neighbor_body(tmp_path):
    project_db = tmp_path / "project.db"
    global_db = tmp_path / "global.db"
    pc = _init_db(project_db)
    gc = _init_db(global_db)
    # Seed a global memory entry the project will edge to.
    global_entry_id = _insert(global_db, text="Avoid commits on Fridays", kind="user")
    # Edge lives in the GLOBAL DB (edges live with their src).
    insert_edge(gc, src_id=global_entry_id, src_scope="entry@global",
                dst_id=42, dst_scope="entry@project",
                type="applies_to", created_by="user")

    # Project-side retrieval asks: who points at this project entry?
    hits = resolve_cross_scope_neighbors(
        project_conn=pc, global_conn=gc,
        dst_refs=[(42, "entry@project")],
        type="applies_to",
    )
    assert len(hits) == 1
    assert hits[0].body == "Avoid commits on Fridays"
    assert hits[0].src_scope == "entry@global"
    pc.close()
    gc.close()


def test_silently_drops_unresolvable_dst(tmp_path):
    project_db = tmp_path / "project.db"
    global_db = tmp_path / "global.db"
    pc = _init_db(project_db)
    gc = _init_db(global_db)
    # Edge points at a project entry that was pruned / never existed.
    insert_edge(gc, src_id=999, src_scope="entry@global",
                dst_id=77, dst_scope="entry@project",
                type="applies_to", created_by="user")
    hits = resolve_cross_scope_neighbors(
        project_conn=pc, global_conn=gc,
        dst_refs=[(77, "entry@project")],
        type="applies_to",
    )
    # The edge's dst can't be resolved (no entry id=77 in project DB), so drop.
    assert hits == []
    pc.close()
    gc.close()


def test_resolves_project_neighbor_in_global_query(tmp_path):
    # Reverse direction: edge lives in project, points at global.
    project_db = tmp_path / "project.db"
    global_db = tmp_path / "global.db"
    pc = _init_db(project_db)
    gc = _init_db(global_db)
    global_entry_id = _insert(global_db, text="Prefer ripgrep", kind="user")
    project_entry_id = _insert(project_db, text="Uses grep for code search", kind="project")
    # Edge lives in PROJECT DB (src is project).
    insert_edge(pc, src_id=project_entry_id, src_scope="entry@project",
                dst_id=global_entry_id, dst_scope="entry@global",
                type="applies_to", created_by="user")
    # Someone looking at the global entry wants: "what project-side things apply to me?"
    hits = resolve_cross_scope_neighbors(
        project_conn=pc, global_conn=gc,
        dst_refs=[(global_entry_id, "entry@global")],
        type="applies_to",
    )
    assert len(hits) == 1
    assert hits[0].body == "Uses grep for code search"
    assert hits[0].src_scope == "entry@project"
    pc.close()
    gc.close()


def test_empty_dst_refs_returns_empty(tmp_path):
    project_db = tmp_path / "p.db"
    global_db = tmp_path / "g.db"
    pc = _init_db(project_db)
    gc = _init_db(global_db)
    hits = resolve_cross_scope_neighbors(
        project_conn=pc, global_conn=gc, dst_refs=[], type="applies_to",
    )
    assert hits == []
    pc.close()
    gc.close()
