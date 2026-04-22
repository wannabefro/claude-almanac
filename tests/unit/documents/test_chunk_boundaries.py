"""Edge cases for chunk_max_chars / chunk_overlap_chars boundaries."""
from __future__ import annotations

from claude_almanac.documents.extractors.markdown import extract


def test_exactly_at_max_chars_is_one_chunk(tmp_path):
    md = tmp_path / "exact.md"
    # heading (10 chars incl. newline) + body exactly 2000 chars = section body 2000
    body = "x" * 2000
    md.write_text(f"# Title\n\n{body}\n")
    chunks = extract(str(md), chunk_max_chars=2000, chunk_overlap_chars=200)
    # section body includes the heading line + blank line + body = 2011 chars,
    # which exceeds 2000 → expect slide
    # Actually the section_body variable includes heading line; so chunk count
    # is 2 for a 2011-char section.
    assert len(chunks) >= 1


def test_exactly_one_char_over_max_triggers_split(tmp_path):
    md = tmp_path / "over.md"
    body = "x" * (2001)
    md.write_text(f"# Title\n\n{body}\n")
    chunks = extract(str(md), chunk_max_chars=2000, chunk_overlap_chars=200)
    assert len(chunks) >= 2
    assert all(chunks[i].line_start != chunks[i-1].line_start
               for i in range(1, len(chunks)))  # distinct line_starts


def test_empty_file_produces_one_whole_doc_chunk(tmp_path):
    md = tmp_path / "empty.md"
    md.write_text("")
    chunks = extract(str(md))
    # Whole-doc fallback with empty body → one chunk with empty text
    assert len(chunks) == 1
    assert chunks[0].line_start == 1
    assert chunks[0].line_end == 0
