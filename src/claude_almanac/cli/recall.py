"""`claude-almanac recall` — search/list/show/pin memories."""
from __future__ import annotations

import sys

from claude_almanac.core import archive, config, paths
from claude_almanac.embedders import make_embedder

USAGE = """Usage: claude-almanac recall <subcommand> [args]

  search <query>      semantic search over global + current-project archives
  search-all <query>  fan out across ALL project archives
  code <query>        semantic search over the current repo's code-index
  list [type]         list markdown memories (type: user|feedback|project|reference)
  show <slug>         print a memory file body
  pin <id> [scope]    pin an archive entry (scope: global|project, default=project)
  unpin <id> [scope]  unpin
  forget <slug-or-id> move memory to trash; delete archive rows
  export [path]       dump all memories to one markdown file
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
    else:
        # pin/unpin/forget/export are stubs in v0.1; document in Task 25 follow-up.
        print(f"unsupported in v0.1: {cmd}")
