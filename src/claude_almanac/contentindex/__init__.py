"""Shared content-index engine (v0.4).

Unified sqlite-vec retrieval plumbing shared by codeindex/ (kind='sym',
'arch') and documents/ (kind='doc'). See docs/superpowers/specs/
2026-04-21-v0.4-documents-and-engine-refactor-design.md for design rationale.

The re-exports below (``init_db``, ``vector_search``, ``upsert``, ``rrf``,
``keyword_search``, ``resolve_min_confidence``, ``search_and_format``) are
a forward-looking engine surface for v0.4. Today's callers — codeindex
internals and the retrieve hook — still reach in via the module-level form
(``from claude_almanac.contentindex import db, search, keyword``); the
re-exported names become load-bearing in Tasks 5/6 when ``documents/``
arrives and needs a stable public API to depend on. Left in deliberately
so the engine surface doesn't churn when documents/ lands.
"""
from __future__ import annotations

from .db import init as init_db
from .db import search as vector_search
from .db import upsert
from .fuse import rrf
from .keyword import search as keyword_search
from .search import (
    resolve_min_confidence,
    search_and_format,
)

__all__ = [
    "init_db", "vector_search", "upsert", "rrf",
    "keyword_search", "resolve_min_confidence", "search_and_format",
]
