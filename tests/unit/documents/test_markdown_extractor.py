"""Markdown extractor — heading parsing, breadcrumb, sliding-window fallback."""
from __future__ import annotations

from pathlib import Path

from claude_almanac.documents.extractors.base import DocChunk
from claude_almanac.documents.extractors.markdown import extract

FIXTURES = Path(__file__).parent / "fixtures"


def test_simple_doc_splits_at_headings():
    chunks = extract(str(FIXTURES / "simple.md"))
    names = [c.symbol_name for c in chunks]
    # Five chunks: Overview, Installation, Usage, Advanced usage, FAQ, Is it fast?
    assert "Overview" in names
    assert "Installation" in names
    assert "Usage" in names
    assert "Advanced usage" in names
    assert "FAQ" in names
    assert "Is it fast?" in names
    assert all(isinstance(c, DocChunk) for c in chunks)


def test_breadcrumb_joins_heading_ancestors():
    chunks = extract(str(FIXTURES / "simple.md"))
    by_name = {c.symbol_name: c for c in chunks}
    # "Advanced usage" (H3) lives under "Usage" (H2) which is under the H1 "Overview"
    assert by_name["Advanced usage"].breadcrumb == "Overview > Usage > Advanced usage"
    # "Is it fast?" (H3) under "FAQ" (H2) under "Overview" (H1)
    assert by_name["Is it fast?"].breadcrumb == "Overview > FAQ > Is it fast?"


def test_breadcrumb_top_level_is_just_heading():
    chunks = extract(str(FIXTURES / "single_h1.md"))
    assert len(chunks) == 1
    assert chunks[0].breadcrumb == "Only One Heading"
    assert chunks[0].symbol_name == "Only One Heading"


def test_no_headings_falls_back_to_whole_doc():
    chunks = extract(str(FIXTURES / "no_headings.md"))
    assert len(chunks) == 1
    assert chunks[0].symbol_name == "no_headings.md"
    assert chunks[0].breadcrumb == "no_headings.md"
    assert chunks[0].line_start == 1


def test_level_4_headings_stay_in_parent_body():
    chunks = extract(str(FIXTURES / "deep_nesting.md"))
    names = [c.symbol_name for c in chunks]
    # "Deeper (level 4 stays in leaf body)" must NOT be its own chunk
    assert "Leaf" in names
    assert not any("Deeper" in n for n in names)
    # The Leaf chunk's text should include the H4 heading line
    leaf = next(c for c in chunks if c.symbol_name == "Leaf")
    assert "#### Deeper" in leaf.text or "Deeper" in leaf.text


def test_line_range_closes_at_next_same_or_higher_heading():
    chunks = extract(str(FIXTURES / "deep_nesting.md"))
    by_name = {c.symbol_name: c for c in chunks}
    top = by_name["Top"]
    mid = by_name["Mid"]
    assert top.line_start == 1
    # Top's H1 body ends at the line before the next H1, but since there is
    # no second H1, it runs to Mid's opening (exclusive).
    assert top.line_end >= top.line_start
    # Mid starts after Top
    assert mid.line_start > top.line_start
    # Mid ends before Second Mid
    second_mid = by_name["Second Mid"]
    assert mid.line_end < second_mid.line_start


def test_oversized_section_splits_with_sliding_window():
    chunks = extract(
        str(FIXTURES / "oversized.md"),
        chunk_max_chars=2000,
        chunk_overlap_chars=200,
    )
    # 3000 chars / (2000 - 200 overlap) = at least 2 chunks
    big_chunks = [c for c in chunks if c.symbol_name.startswith("Big Section")]
    assert len(big_chunks) >= 2
    # Names should be "Big Section (part 1)", "Big Section (part 2)", ...
    for i, c in enumerate(big_chunks, start=1):
        assert f"(part {i})" in c.symbol_name
    # First chunk starts at the heading line (1)
    assert big_chunks[0].line_start == 1


def test_oversized_section_overlap_chars_present():
    """The 200-char overlap should mean the end of chunk 1 appears at the
    start of chunk 2's body (after breadcrumb)."""
    chunks = extract(
        str(FIXTURES / "oversized.md"),
        chunk_max_chars=2000, chunk_overlap_chars=200,
    )
    big = [c for c in chunks if c.symbol_name.startswith("Big Section")]
    # tail of chunk 1 must appear in head of chunk 2
    tail1 = big[0].text[-200:]
    head2 = big[1].text[:400]  # headline + overlap
    # some portion of tail1 should appear in head2 (weak equality — just assert they share 50 chars)
    assert any(tail1[i:i+50] in head2 for i in range(0, 150, 10))


def test_mdx_suffix_parsed_identically(tmp_path):
    mdx = tmp_path / "same.mdx"
    mdx.write_text("# Heading\n\nBody.\n")
    chunks = extract(str(mdx))
    assert len(chunks) == 1
    assert chunks[0].symbol_name == "Heading"


def test_hash_lines_inside_fenced_code_block_do_not_split(tmp_path):
    """ATX-regex approach would have split here; CommonMark parser does not."""
    md = tmp_path / "fenced.md"
    md.write_text(
        "# Real Heading\n"
        "\n"
        "```python\n"
        "# This is a comment, not a heading\n"
        "## Neither is this\n"
        "x = 1\n"
        "```\n"
        "\n"
        "Real body continues.\n"
    )
    chunks = extract(str(md))
    names = [c.symbol_name for c in chunks]
    assert names == ["Real Heading"]
    assert "comment" not in " ".join(names)
    # The fenced block content stays inside the Real Heading chunk
    assert "# This is a comment" in chunks[0].text


def test_sliding_window_line_starts_unique_on_short_line_range(tmp_path):
    """When a heading's line span is shorter than the number of sub-chunks,
    each sub-chunk must still get a unique line_start so the doc unique
    index in contentindex.db holds."""
    md = tmp_path / "collapsed.md"
    # Single-line heading + single-line 6000-char body → 1-line line range but
    # 4 sliding-window parts at chunk_max=2000, overlap=200.
    blob = "x" * 6000
    md.write_text(f"# Collapsed\n{blob}\n")
    chunks = extract(str(md), chunk_max_chars=2000, chunk_overlap_chars=200)
    line_starts = [c.line_start for c in chunks]
    assert len(line_starts) == len(set(line_starts)), (
        f"duplicate line_starts: {line_starts}"
    )
    assert len(chunks) >= 4


def test_yaml_frontmatter_closing_dashes_do_not_split(tmp_path):
    """YAML frontmatter ends with '---' which markdown-it reads as a setext
    H2 underline. We filter to ATX-only so these don't false-split."""
    md = tmp_path / "with_frontmatter.md"
    md.write_text(
        "---\n"
        "title: My Doc\n"
        "author: Someone\n"
        "---\n"
        "\n"
        "# Real Heading\n"
        "\n"
        "Body.\n"
    )
    chunks = extract(str(md))
    names = [c.symbol_name for c in chunks]
    # Only the ATX heading should produce a chunk
    assert names == ["Real Heading"]


def test_setext_h1_ignored(tmp_path):
    """Standalone setext H1 (Title\\n=====) is not indexed; chunking is
    ATX-only by design per the v0.4 spec."""
    md = tmp_path / "setext.md"
    md.write_text(
        "Title Goes Here\n"
        "===============\n"
        "\n"
        "Body of the section.\n"
        "\n"
        "# ATX After\n"
        "\n"
        "More body.\n"
    )
    chunks = extract(str(md))
    names = [c.symbol_name for c in chunks]
    # Setext heading ignored → text before the first ATX heading falls into
    # the whole-doc fallback ONLY if there are no ATX headings. Here there
    # is one ATX heading, so the setext-H1's pre-body gets orphaned (no
    # chunk for it). That's acceptable for v0.4; setext is explicitly
    # out of scope.
    assert "ATX After" in names
    assert "Title Goes Here" not in names
