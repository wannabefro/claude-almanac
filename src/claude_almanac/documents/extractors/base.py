"""Document-extractor data types (v0.4)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DocChunk:
    """One extractable unit of a document — a heading section or a
    sliding-window sub-chunk of an oversized section.

    Attributes:
      symbol_name: heading text (or ``<basename>`` for heading-less files,
        or ``<heading> (part N)`` for sliding-window sub-chunks).
      breadcrumb: heading ancestry joined with ``>`` (or filename for
        heading-less / whole-doc fallback).
      line_start: 1-based line number of the heading (or 1 for
        heading-less / the window's starting line for sub-chunks).
      line_end: 1-based line number of the section's last line (inclusive).
      text: breadcrumb header line + section body, suitable for
        embedding and keyword matching. Format:
          // <file_path> [doc] <breadcrumb>
          <body>
    """
    symbol_name: str
    breadcrumb: str
    line_start: int
    line_end: int
    text: str
