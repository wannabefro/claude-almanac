"""`claude-almanac recall` — search/list/show/pin memories."""
from __future__ import annotations

import sys
import time as _time
from datetime import date as _date
from pathlib import Path

from claude_almanac.core import archive, config, paths
from claude_almanac.embedders import make_embedder

USAGE = """Usage: claude-almanac recall <subcommand> [args]

  search <query>          semantic search over global + current-project archives
  search-all <query>      fan out across ALL project archives
  code <query>            semantic search over the current repo's code-index
  list [type]             list markdown memories (type: user|feedback|project|reference)
  show <slug>             print a memory file body
  history <slug>          print version history of a memory
  correct <slug> [--body TEXT]   supersede a memory's body (default: open $EDITOR)

  pin <id-or-slug>        pin an archive entry (global + project scopes)
  unpin <id-or-slug>      unpin
  forget <slug>           move memory to trash dir (keeps a recoverable copy)
  export [path]           dump memories to one markdown file; default scope: global+project

  link <slug-a> <slug-b>           create a symmetric 'related' edge between two slugs
  supersede <new-slug> <old-slug>  mark new-slug as superseding old-slug (one-way)
  unlink <slug-a> <slug-b> [--type TYPE]  remove edge(s) between two slugs
  links <slug>                     show incoming and outgoing edges for a slug
  rollups <query>                  semantic search over session rollups
  rollup-now                       manually trigger a rollup for the current session
"""


def _print_hits(hits: list[archive.Hit]) -> None:
    for h in hits:
        preview = h.text.strip().splitlines()[0] if h.text.strip() else ""
        print(f"- [{h.kind}] {h.source} {preview}")


def _search(query: str, *, all_projects: bool) -> None:
    cfg = config.load()
    embedder = make_embedder(cfg.embedder.provider, cfg.embedder.model)
    [vec] = embedder.embed([query])
    global_db = paths.global_memory_dir() / "archive.db"
    archive.init(
        global_db,
        embedder_name=embedder.name,
        model=cfg.embedder.model,
        dim=embedder.dim,
        distance=embedder.distance,
    )
    dbs = [global_db]
    if all_projects:
        projs = paths.projects_memory_dir()
        if projs.exists():
            for d in projs.iterdir():
                if d.is_dir():
                    db = d / "archive.db"
                    if db.exists():
                        dbs.append(db)
    else:
        proj_db = paths.project_memory_dir() / "archive.db"
        if proj_db.exists():
            dbs.append(proj_db)

    hits: list[archive.Hit] = []
    for db in dbs:
        hits.extend(archive.search(db, query_embedding=vec, top_k=cfg.retrieval.top_k))
    hits.sort(key=lambda h: h.distance)
    _print_hits(hits[: cfg.retrieval.top_k])


def _list(kind_filter: str | None) -> None:
    for scope_dir in (paths.global_memory_dir(), paths.project_memory_dir()):
        if not scope_dir.exists():
            continue
        for md in sorted(scope_dir.glob("*.md")):
            if kind_filter and not md.name.startswith(f"{kind_filter}_"):
                continue
            print(f"{md.name}")


def _show(slug: str) -> None:
    for scope_dir in (paths.global_memory_dir(), paths.project_memory_dir()):
        candidate = scope_dir / slug
        if candidate.exists():
            print(candidate.read_text())
            return
    print(f"not found: {slug}")


def _history(slug: str) -> None:
    from datetime import datetime as _dt

    from claude_almanac.core import versioning
    # Look in global then project scope. First scope with the slug wins.
    for scope_dir in (paths.global_memory_dir(), paths.project_memory_dir()):
        db = scope_dir / "archive.db"
        if not db.exists():
            continue
        chain = versioning.list_versions(db, slug=slug)
        if chain:
            n = len(chain)
            plural = "s" if n != 1 else ""
            print(f"Version history for '{slug}' ({n} version{plural})")
            print()
            for v in chain:
                marker = " (current)" if v.is_current else ""
                orig = _dt.fromtimestamp(v.original_created_at).strftime(
                    "%Y-%m-%d %H:%M"
                )
                header = (
                    f"v{v.version}{marker}  created={orig}  "
                    f"provenance={v.provenance}"
                )
                if v.superseded_at is not None:
                    sup = _dt.fromtimestamp(v.superseded_at).strftime(
                        "%Y-%m-%d %H:%M"
                    )
                    header += f"  superseded={sup}"
                print(header)
                for line in v.text.splitlines():
                    print(f"  {line}")
                print()
            return
    print(f"error: no memory found with slug {slug!r}", file=sys.stderr)
    sys.exit(1)


def _open_editor_with_text(initial: str) -> str:
    """Open $EDITOR with `initial` as the starting content; return the saved content.

    Falls back to vi if EDITOR is unset. Raises SystemExit(1) if the editor
    exits nonzero or the user leaves the file empty.
    """
    import os
    import shlex
    import subprocess
    import tempfile
    editor = os.environ.get("EDITOR", "vi")
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
        f.write(initial)
        tmp_path = f.name
    editor_cmd = shlex.split(editor) + [tmp_path]
    try:
        try:
            result = subprocess.run(editor_cmd)
        except FileNotFoundError:
            sys.stderr.write(f"correct: editor not found: {editor!r}\n")
            sys.exit(1)
        if result.returncode != 0:
            sys.stderr.write(f"editor exited with code {result.returncode}\n")
            sys.exit(1)
        with open(tmp_path) as f:
            new_text = f.read()
    finally:
        os.unlink(tmp_path)
    if not new_text.strip():
        sys.stderr.write("correct: empty body, aborting\n")
        sys.exit(1)
    return new_text


def _correct(slug: str, *, body: str | None) -> None:
    from claude_almanac.core import versioning
    # Locate the slug in project scope first, then global
    for scope_dir in (paths.project_memory_dir(), paths.global_memory_dir()):
        db = scope_dir / "archive.db"
        if not db.exists():
            continue
        chain = versioning.list_versions(db, slug=slug)
        if chain:
            current_text = chain[0].text
            current_kind = chain[0].kind
            new_text = body if body is not None else _open_editor_with_text(current_text)
            if new_text == current_text:
                print(f"correct: {slug} is already that body; no change")
                return
            cfg = config.load()
            embedder = make_embedder(cfg.embedder.provider, cfg.embedder.model)
            [vec] = embedder.embed([new_text])
            versioning.snapshot_then_replace(
                db, scope_dir=scope_dir, slug=slug,
                new_text=new_text, new_kind=current_kind,
                new_embedding=vec, provenance="correct",
            )
            print(f"corrected {slug}")
            return
    print(f"error: no memory found with slug {slug!r}", file=sys.stderr)
    sys.exit(1)


def _cmd_code(argv: list[str]) -> int:
    if not argv:
        print("usage: recall code <query>", file=sys.stderr)
        return 2
    from claude_almanac.codeindex import search as _ci_search
    dbp = paths.project_memory_dir() / "code-index.db"
    if not dbp.exists():
        print("no code-index.db — run `claude-almanac codeindex init`")
        return 1
    cfg = config.load()
    embedder = make_embedder(cfg.embedder.provider, cfg.embedder.model)
    [vec] = embedder.embed([" ".join(argv)])
    out = _ci_search.search_and_format(str(dbp), query_vec=vec, sym_k=3, arch_k=2)
    print(out or "(no matches)")
    return 0


def _set_pinned_across_scopes(target: str, pinned: bool) -> int:
    """Try target as int rowid first (per-scope), else as slug.

    Returns total rows updated across both scopes.
    """
    total = 0
    dbs = [paths.global_memory_dir() / "archive.db",
           paths.project_memory_dir() / "archive.db"]
    for db in dbs:
        if not db.exists():
            continue
        try:
            rowid = int(target)
            total += archive.set_pinned(db, row_id=rowid, pinned=pinned)
        except ValueError:
            total += archive.set_pinned_by_slug(db, slug=target, pinned=pinned)
    return total


def _cmd_pin(args: list[str], *, pinned: bool) -> None:
    if not args:
        print(USAGE)
        sys.exit(2)
    target = args[0]
    n = _set_pinned_across_scopes(target, pinned)
    verb = "pinned" if pinned else "unpinned"
    if n == 0:
        print(f"no match for {target!r}")
        sys.exit(1)
    print(f"{verb} {n} row(s) for {target!r}")


def _scopes_containing_slug(slug: str) -> list[tuple[str, Path]]:
    """Return [(name, scope_dir)] for scopes whose directory has <scope>/<slug>."""
    out: list[tuple[str, Path]] = []
    for name, sd in (
        ("global", paths.global_memory_dir()),
        ("project", paths.project_memory_dir()),
    ):
        if (sd / slug).exists():
            out.append((name, sd))
    return out


def _cmd_forget(args: list[str]) -> None:
    scope_filter: str | None = None
    positional: list[str] = []
    i = 0
    while i < len(args):
        if args[i] == "--scope" and i + 1 < len(args):
            scope_filter = args[i + 1]
            i += 2
            continue
        positional.append(args[i])
        i += 1
    if not positional:
        print(USAGE)
        sys.exit(2)
    slug = positional[0]
    candidates = _scopes_containing_slug(slug)
    if scope_filter:
        candidates = [c for c in candidates if c[0] == scope_filter]
    if not candidates:
        print(f"no memory file named {slug!r}")
        sys.exit(1)
    if len(candidates) > 1 and not scope_filter:
        print(
            f"{slug!r} exists in multiple scopes; pass --scope global|project",
            file=sys.stderr,
        )
        sys.exit(2)
    ts = _time.strftime("%Y%m%d-%H%M%S")
    for name, scope_dir in candidates:
        trash = scope_dir / "trash"
        trash.mkdir(parents=True, exist_ok=True)
        src = scope_dir / slug
        dst = trash / f"{slug}.{ts}"
        src.rename(dst)
        db = scope_dir / "archive.db"
        if db.exists():
            archive.delete_by_slug(db, slug=slug)
        print(f"forgot {name}/{slug} -> trash/{dst.name}")


def _collect_scope_mds(scope_dir: Path, scope_label: str) -> list[tuple[str, str]]:
    """Return [(header, body)] for each *.md directly under scope_dir (excludes trash/)."""
    out: list[tuple[str, str]] = []
    if not scope_dir.exists():
        return out
    for md in sorted(scope_dir.glob("*.md")):
        header = f"# {scope_label}/{md.name}"
        out.append((header, md.read_text()))
    return out


def _cmd_export(args: list[str]) -> None:
    include_global = False
    include_project = False
    include_all = False
    positional: list[str] = []
    for a in args:
        if a == "--global":
            include_global = True
        elif a == "--project":
            include_project = True
        elif a == "--all":
            include_all = True
        else:
            positional.append(a)
    if not (include_global or include_project or include_all):
        include_global = include_project = True  # default
    out_path = (
        Path(positional[0])
        if positional
        else Path.cwd() / f"claude-almanac-export-{_date.today().isoformat()}.md"
    )
    sections: list[tuple[str, str]] = []
    if include_global or include_all:
        sections.extend(_collect_scope_mds(paths.global_memory_dir(), "global"))
    if include_project and not include_all:
        sections.extend(_collect_scope_mds(paths.project_memory_dir(), "project"))
    if include_all:
        projs_root = paths.projects_memory_dir()
        if projs_root.exists():
            for d in sorted(projs_root.iterdir()):
                if d.is_dir():
                    sections.extend(_collect_scope_mds(d, f"project:{d.name}"))
    body = "\n\n---\n\n".join(f"{h}\n\n{b}" for h, b in sections)
    out_path.write_text(body)
    n = len(sections)
    print(f"exported {n} memor{'y' if n == 1 else 'ies'} to {out_path}")


def _cmd_link(args: list[str]) -> None:
    """Create a symmetric 'related' edge between two slugs."""
    import sqlite3

    from claude_almanac.core.archive import lookup_entry_id_by_slug
    from claude_almanac.edges.store import insert_edge

    if len(args) < 2:
        print("usage: recall link <slug-a> <slug-b>", file=sys.stderr)
        sys.exit(2)
    slug_a, slug_b = args[0], args[1]
    db = paths.project_memory_dir() / "archive.db"
    conn = sqlite3.connect(db)
    try:
        a = lookup_entry_id_by_slug(conn, slug_a)
        b = lookup_entry_id_by_slug(conn, slug_b)
        if a is None:
            print(f"error: unknown slug: {slug_a}", file=sys.stderr)
            sys.exit(1)
        if b is None:
            print(f"error: unknown slug: {slug_b}", file=sys.stderr)
            sys.exit(1)
        insert_edge(conn, a, "entry@project", b, "entry@project", "related", "user")
        insert_edge(conn, b, "entry@project", a, "entry@project", "related", "user")
    finally:
        conn.close()
    print(f"linked: {slug_a} <-> {slug_b}")


def _cmd_supersede(args: list[str]) -> None:
    """Create a supersedes edge: new_slug replaces old_slug (one-directional)."""
    import sqlite3

    from claude_almanac.core.archive import lookup_entry_id_by_slug
    from claude_almanac.edges.store import insert_edge

    if len(args) < 2:
        print("usage: recall supersede <new-slug> <old-slug>", file=sys.stderr)
        sys.exit(2)
    new_slug, old_slug = args[0], args[1]
    db = paths.project_memory_dir() / "archive.db"
    conn = sqlite3.connect(db)
    try:
        n = lookup_entry_id_by_slug(conn, new_slug)
        o = lookup_entry_id_by_slug(conn, old_slug)
        if n is None:
            print(f"error: unknown slug: {new_slug}", file=sys.stderr)
            sys.exit(1)
        if o is None:
            print(f"error: unknown slug: {old_slug}", file=sys.stderr)
            sys.exit(1)
        insert_edge(conn, n, "entry@project", o, "entry@project", "supersedes", "user")
    finally:
        conn.close()
    print(f"{new_slug} supersedes {old_slug}")


def _cmd_unlink(args: list[str]) -> None:
    """Remove edge(s) between two slugs."""
    import sqlite3

    from claude_almanac.core.archive import lookup_entry_id_by_slug
    from claude_almanac.edges.store import delete_edge

    edge_type = "related"
    positional: list[str] = []
    i = 0
    while i < len(args):
        if args[i] == "--type" and i + 1 < len(args):
            edge_type = args[i + 1]
            i += 2
        else:
            positional.append(args[i])
            i += 1
    if len(positional) < 2:
        print("usage: recall unlink <slug-a> <slug-b> [--type TYPE]", file=sys.stderr)
        sys.exit(2)
    slug_a, slug_b = positional[0], positional[1]
    db = paths.project_memory_dir() / "archive.db"
    conn = sqlite3.connect(db)
    try:
        a = lookup_entry_id_by_slug(conn, slug_a)
        b = lookup_entry_id_by_slug(conn, slug_b)
        if a is None or b is None:
            print("error: unknown slug", file=sys.stderr)
            sys.exit(1)
        delete_edge(conn, a, "entry@project", b, "entry@project", edge_type)
        if edge_type == "related":
            delete_edge(conn, b, "entry@project", a, "entry@project", edge_type)
    finally:
        conn.close()
    print(f"unlinked: {slug_a} / {slug_b} [{edge_type}]")


def _cmd_links(args: list[str]) -> None:
    """Show incoming and outgoing edges for a slug."""
    import sqlite3

    from claude_almanac.core.archive import lookup_entry_id_by_slug
    from claude_almanac.edges.store import neighbors

    if not args:
        print("usage: recall links <slug>", file=sys.stderr)
        sys.exit(2)
    slug = args[0]
    db = paths.project_memory_dir() / "archive.db"
    conn = sqlite3.connect(db)
    try:
        sid = lookup_entry_id_by_slug(conn, slug)
        if sid is None:
            print(f"error: unknown slug: {slug}", file=sys.stderr)
            sys.exit(1)
        outgoing = neighbors(conn, [(sid, "entry@project")])
        incoming = conn.execute(
            "SELECT src_id, src_scope, type, created_by FROM edges "
            "WHERE dst_id=? AND dst_scope=?",
            (sid, "entry@project"),
        ).fetchall()
    finally:
        conn.close()
    print(f"Outgoing from {slug}:")
    for e in outgoing:
        print(f"  \u2192 [{e.type}] dst={e.dst_id} ({e.dst_scope}) by {e.created_by}")
    print(f"Incoming to {slug}:")
    for src_id, src_scope, etype, by in incoming:
        print(f"  \u2190 [{etype}] src={src_id} ({src_scope}) by {by}")


def _cmd_rollups(args: list[str]) -> None:
    """Semantic search over session rollups."""
    topk = 5
    positional: list[str] = []
    i = 0
    while i < len(args):
        if args[i] == "--topk" and i + 1 < len(args):
            topk = int(args[i + 1])
            i += 2
        else:
            positional.append(args[i])
            i += 1
    if not positional:
        print("usage: recall rollups <query> [--topk N]", file=sys.stderr)
        sys.exit(2)
    query = " ".join(positional)
    cfg = config.load()
    embedder = make_embedder(cfg.embedder.provider, cfg.embedder.model)
    [query_vec] = embedder.embed([query])
    db = paths.project_memory_dir() / "archive.db"
    results = archive.search_rollups(db, query_embedding=query_vec, topk=topk)
    if not results:
        print("(no rollups found)")
        return
    for rid, dist, narrative in results:
        print(f"[rollup {rid}] distance={dist:.3f}")
        print(f"  {narrative[:400]}")


def _cmd_rollup_now() -> None:
    """Manually trigger a rollup for the current session's transcript."""
    import subprocess

    cwd = Path.cwd()
    encoded = str(cwd).replace("/", "-")
    tdir = Path.home() / ".claude" / "projects" / encoded
    if not tdir.exists():
        print(
            f"error: no transcripts found for {cwd} (expected {tdir})",
            file=sys.stderr,
        )
        sys.exit(1)
    transcripts = sorted(
        tdir.glob("*.jsonl"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not transcripts:
        print(f"error: no transcript files in {tdir}", file=sys.stderr)
        sys.exit(1)
    newest = transcripts[0]
    subprocess.run(
        [
            sys.executable,
            "-m",
            "claude_almanac.rollups.runner",
            "--trigger",
            "explicit",
            "--transcript",
            str(newest),
            "--session-id",
            newest.stem,
            "--cwd",
            str(cwd),
        ],
        check=True,
    )
    print(f"rollup generated for session {newest.stem}")


def run(argv: list[str]) -> None:
    if not argv:
        print(USAGE)
        return
    cmd, *rest = argv
    if cmd == "search":
        _search(" ".join(rest), all_projects=False)
    elif cmd == "search-all":
        _search(" ".join(rest), all_projects=True)
    elif cmd == "code":
        _cmd_code(rest)
    elif cmd == "list":
        _list(rest[0] if rest else None)
    elif cmd == "show":
        if not rest:
            print("show requires a slug")
            return
        _show(rest[0])
    elif cmd == "history":
        if len(rest) < 1:
            sys.stderr.write("history: missing <slug>\n")
            sys.exit(2)
        _history(rest[0])
    elif cmd == "correct":
        if len(rest) < 1:
            sys.stderr.write("correct: missing <slug>\n")
            sys.exit(2)
        slug = rest[0]
        body: str | None = None
        if "--body" in rest:
            idx = rest.index("--body")
            if idx + 1 >= len(rest):
                sys.stderr.write("correct: --body needs a value\n")
                sys.exit(2)
            body = rest[idx + 1]
        _correct(slug, body=body)
    elif cmd == "pin":
        _cmd_pin(rest, pinned=True)
    elif cmd == "unpin":
        _cmd_pin(rest, pinned=False)
    elif cmd == "forget":
        _cmd_forget(rest)
    elif cmd == "export":
        _cmd_export(rest)
    elif cmd == "link":
        _cmd_link(rest)
    elif cmd == "supersede":
        _cmd_supersede(rest)
    elif cmd == "unlink":
        _cmd_unlink(rest)
    elif cmd == "links":
        _cmd_links(rest)
    elif cmd == "rollups":
        _cmd_rollups(rest)
    elif cmd == "rollup-now":
        _cmd_rollup_now()
    else:
        print(f"unknown subcommand: {cmd}", file=sys.stderr)
        print(USAGE)
