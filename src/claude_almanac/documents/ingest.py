"""Walk a repo, extract markdown chunks, embed, upsert into the
content-index DB with kind='doc' (v0.4).
"""
from __future__ import annotations

import posixpath
from pathlib import Path, PurePosixPath
from typing import Any

from claude_almanac.codeindex.config import (
    DEFAULT_DOC_EXCLUDES,
    DEFAULT_EXCLUDES,
    _excluded,
)
from claude_almanac.codeindex.log import emit
from claude_almanac.contentindex import db as _db
from claude_almanac.core import paths
from claude_almanac.documents.extractors.markdown import extract

_DOC_EXTS = {".md", ".mdx"}


def _discover(
    repo_root: str, patterns: list[str], excludes: list[str],
) -> list[str]:
    """Return list of repo-root-relative POSIX paths matching any glob
    in ``patterns`` and not matching any glob in ``excludes + DEFAULT_EXCLUDES``.
    """
    root = Path(repo_root)
    all_excludes = DEFAULT_EXCLUDES + DEFAULT_DOC_EXCLUDES + list(excludes)
    seen: set[str] = set()
    for pat in patterns:
        for match in root.glob(pat):
            if not match.is_file():
                continue
            if match.suffix.lower() not in _DOC_EXTS:
                continue
            rel = str(PurePosixPath(match.relative_to(root)))
            if _excluded(rel, all_excludes):
                continue
            seen.add(rel)
    return sorted(seen)


def index_repo(
    *,
    repo_root: str,
    db_path: str,
    embedder: Any,
    patterns: list[str] | None = None,
    excludes: list[str] | None = None,
    chunk_max_chars: int,
    chunk_overlap_chars: int,
    commit_sha: str,
    only_files: list[str] | None = None,
) -> int:
    """Walk the repo, extract + embed + upsert every matching file.

    Returns total chunk count written. Non-incremental when
    ``only_files`` is ``None`` — callers should use
    :func:`claude_almanac.documents.refresh.refresh_repo` to skip
    unchanged files.

    When ``only_files`` is supplied, ``patterns``/``excludes`` are
    ignored and the given list is ingested verbatim (relative POSIX
    paths). Used by ``refresh_repo`` to re-ingest only changed files
    without rescanning the whole repo.
    """
    if only_files is not None:
        rel_paths = list(only_files)
    else:
        assert patterns is not None, "patterns required when only_files is None"
        rel_paths = _discover(repo_root, patterns, excludes or [])

    log_path = paths.logs_dir() / "content-index.log"
    total = 0
    for rel in rel_paths:
        abs_path = str(Path(repo_root) / rel)
        chunks = extract(
            abs_path,
            chunk_max_chars=chunk_max_chars,
            chunk_overlap_chars=chunk_overlap_chars,
            file_rel=rel,
        )
        if not chunks:
            continue
        texts = [c.text for c in chunks]
        try:
            vecs = embedder.embed(texts)
        except Exception as e:
            # Embedder-level failures shouldn't kill the whole ingest;
            # log structured event and skip the file. Mirrors
            # codeindex/sym.py::extract_file's error handling so Task 8's
            # dogfood run is debuggable if Ollama is down.
            emit(
                log_path,
                component="documents",
                level="error",
                event="doc.embed_fail",
                file=rel,
                err=str(e),
            )
            continue
        module = posixpath.dirname(rel)
        for c, vec in zip(chunks, vecs, strict=True):
            _db.upsert(
                db_path,
                kind="doc",
                text=c.text,
                file_path=rel,
                symbol_name=c.symbol_name,
                module=module,
                line_start=c.line_start,
                line_end=c.line_end,
                commit_sha=commit_sha,
                embedding=vec,
            )
            total += 1
    return total
