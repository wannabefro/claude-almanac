"""Markdown extractor: CommonMark-heading-primary chunking with
sliding-window fallback for oversized sections (v0.4).

Design:
- Splits at CommonMark headings levels 1-3 (``#``, ``##``, ``###``).
  Level 4+ stays as body within the level-3 parent so the chunk
  granularity matches what users typically think of as "a section"
  without over-chunking deeply nested subheadings.
- Uses ``markdown-it-py`` (a real CommonMark parser) so ``#`` lines
  inside fenced code blocks don't produce false heading splits.
- If a section body exceeds ``chunk_max_chars``, subdivides with a
  sliding window (``chunk_overlap_chars`` overlap). Sub-chunk names
  get ``(part N)`` suffix so the unique-key semantics in
  ``contentindex.db`` hold (each sub-chunk has a distinct line_start).
- Heading-less files fall back to one whole-doc chunk named by basename.
"""
from __future__ import annotations

import posixpath
from pathlib import Path

from markdown_it import MarkdownIt

from claude_almanac.documents.extractors.base import DocChunk

_PARSER = MarkdownIt("commonmark")

_DEFAULT_MAX_CHARS = 2000
_DEFAULT_OVERLAP = 200


def _parse_headings(raw: str) -> list[tuple[int, int, str]]:
    """Return list of (line_index_1_based, level, text) for CommonMark
    headings levels 1-3. Levels 4+ are ignored so chunk granularity
    matches typical 'section' mental model. Uses a real CommonMark
    parser so fenced code blocks don't produce false heading splits.
    """
    tokens = _PARSER.parse(raw)
    out: list[tuple[int, int, str]] = []
    for i, tok in enumerate(tokens):
        if tok.type != "heading_open":
            continue
        level = int(tok.tag[1:])  # 'h1' -> 1, 'h2' -> 2, 'h3' -> 3
        if level > 3:
            continue
        # The next token is always 'inline' with content=heading text
        inline = tokens[i + 1]
        text = (inline.content or "").strip()
        if not text:
            continue
        # tok.map is [start_line_0_based, end_line_0_based_exclusive]
        line_1based = tok.map[0] + 1 if tok.map else 0
        if line_1based <= 0:
            continue
        out.append((line_1based, level, text))
    return out


def _build_breadcrumb(
    headings: list[tuple[int, int, str]], idx: int,
) -> str:
    """For the heading at ``headings[idx]``, join all ancestor headings
    (lower level numbers, preceding in order) + this heading with ``>``.
    """
    _, my_level, my_text = headings[idx]
    ancestors: list[str] = []
    current_level = my_level
    for j in range(idx - 1, -1, -1):
        _, lvl, txt = headings[j]
        if lvl < current_level:
            ancestors.append(txt)
            current_level = lvl
            if lvl == 1:
                break
    return " > ".join(list(reversed(ancestors)) + [my_text])


def _sliding_sub_chunks(
    body: str, chunk_max: int, overlap: int,
) -> list[str]:
    """Split ``body`` into overlapping windows of at most ``chunk_max``
    characters. No word-boundary splitting — simple byte-oriented."""
    if len(body) <= chunk_max:
        return [body]
    step = max(chunk_max - overlap, 1)
    out: list[str] = []
    pos = 0
    while pos < len(body):
        out.append(body[pos:pos + chunk_max])
        pos += step
    return out


def extract(
    file_path: str,
    *,
    chunk_max_chars: int = _DEFAULT_MAX_CHARS,
    chunk_overlap_chars: int = _DEFAULT_OVERLAP,
    file_rel: str | None = None,
) -> list[DocChunk]:
    """Extract chunks from a markdown file. ``file_rel`` is the path
    shown in the breadcrumb header — if ``None``, uses the basename
    so unit tests can pass tmp paths.
    """
    p = Path(file_path)
    raw = p.read_text(encoding="utf-8", errors="replace")
    lines = raw.splitlines()
    rel_for_header = file_rel if file_rel is not None else p.name

    headings = _parse_headings(raw)

    if not headings:
        # Whole-doc fallback. May still slide-window if oversized.
        basename = posixpath.basename(rel_for_header)
        body = raw
        return _emit_section(
            symbol_root=basename,
            breadcrumb=basename,
            body=body,
            line_start=1,
            line_end=len(lines),
            rel_for_header=rel_for_header,
            chunk_max=chunk_max_chars,
            overlap=chunk_overlap_chars,
        )

    chunks: list[DocChunk] = []
    for i, (hline, _level, _text) in enumerate(headings):
        next_line = headings[i + 1][0] if i + 1 < len(headings) else len(lines) + 1
        line_start = hline
        line_end = next_line - 1
        section_body = "\n".join(lines[line_start - 1:line_end])
        breadcrumb = _build_breadcrumb(headings, i)
        chunks.extend(_emit_section(
            symbol_root=headings[i][2],
            breadcrumb=breadcrumb,
            body=section_body,
            line_start=line_start,
            line_end=line_end,
            rel_for_header=rel_for_header,
            chunk_max=chunk_max_chars,
            overlap=chunk_overlap_chars,
        ))
    return chunks


def _emit_section(
    *,
    symbol_root: str,
    breadcrumb: str,
    body: str,
    line_start: int,
    line_end: int,
    rel_for_header: str,
    chunk_max: int,
    overlap: int,
) -> list[DocChunk]:
    """Emit one or more DocChunks for a section, applying the
    sliding-window fallback if the body is oversized. The header line
    format matches the sym convention: ``// <file> [doc] <breadcrumb>``."""
    sub_bodies = _sliding_sub_chunks(body, chunk_max, overlap)
    out: list[DocChunk] = []
    if len(sub_bodies) == 1:
        text = f"// {rel_for_header} [doc] {breadcrumb}\n{sub_bodies[0]}"
        out.append(DocChunk(
            symbol_name=symbol_root,
            breadcrumb=breadcrumb,
            line_start=line_start,
            line_end=line_end,
            text=text,
        ))
        return out
    # Multiple parts. Compute per-sub-chunk line_start by walking bodies.
    # Each sub-chunk's line_start is the rough line offset in the section.
    # For uniqueness on (file_path, line_start) we just need distinct
    # starting lines, so we add a step-size increment per part.
    step_lines = max((line_end - line_start + 1) // len(sub_bodies), 1)
    for i, sub in enumerate(sub_bodies, start=1):
        part_line_start = line_start + (i - 1) * step_lines
        # Cap at line_end so part_line_start never exceeds the section.
        part_line_start = min(part_line_start, line_end)
        if i > 1 and part_line_start == out[-1].line_start:
            part_line_start += 1  # forced distinct for unique index
        text = f"// {rel_for_header} [doc] {breadcrumb} (part {i})\n{sub}"
        out.append(DocChunk(
            symbol_name=f"{symbol_root} (part {i})",
            breadcrumb=f"{breadcrumb} (part {i})",
            line_start=part_line_start,
            line_end=line_end,
            text=text,
        ))
    return out
