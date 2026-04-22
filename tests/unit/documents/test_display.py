"""Formatting contract for doc-hit display (v0.4)."""
from __future__ import annotations

from claude_almanac.documents.display import format_doc_hit


def test_format_doc_hit_renders_breadcrumb_and_body():
    hit = {
        "text": "// docs/cli.md [doc] Running\n# Running\n\nUse run().",
        "file_path": "docs/cli.md",
        "line_start": 1,
        "line_end": 5,
    }
    out = format_doc_hit(hit)
    assert out.startswith("- [doc] docs/cli.md:1-5")
    assert "Running" in out
    # First body line after the header line is "# Running"
    assert "# Running" in out


def test_format_doc_hit_handles_missing_header():
    hit = {
        "text": "plain body no header",
        "file_path": "docs/a.md",
        "line_start": 1,
        "line_end": 2,
    }
    out = format_doc_hit(hit)
    # No crumb but still emits something sensible.
    assert "- [doc] docs/a.md:1-2" in out


def test_format_doc_hit_truncates_long_body():
    long_body = "x" * 1000
    hit = {
        "text": f"// docs/a.md [doc] Crumb\n{long_body}",
        "file_path": "docs/a.md",
        "line_start": 1,
        "line_end": 2,
    }
    out = format_doc_hit(hit, body_char_cap=50)
    assert out.count("x") == 50


def test_format_doc_hit_empty_text_safe():
    hit = {
        "text": "",
        "file_path": "docs/a.md",
        "line_start": 1,
        "line_end": 1,
    }
    out = format_doc_hit(hit)
    assert "- [doc] docs/a.md:1-1" in out


def test_format_doc_hit_empty_body_drops_trailing_sentinel():
    hit = {"text": "", "file_path": "docs/a.md", "line_start": 1, "line_end": 1}
    assert format_doc_hit(hit) == "- [doc] docs/a.md:1-1"


def test_format_doc_hit_missing_crumb_only_has_body():
    hit = {
        "text": "first line\nsecond",
        "file_path": "docs/a.md",
        "line_start": 1,
        "line_end": 2,
    }
    # No `// [doc] ...` header → crumb is empty, first body line is "first line".
    assert format_doc_hit(hit) == "- [doc] docs/a.md:1-2 — first line"


def test_format_doc_hit_crumb_without_body():
    hit = {
        "text": "// docs/a.md [doc] Crumb",
        "file_path": "docs/a.md",
        "line_start": 1,
        "line_end": 1,
    }
    # Header line but no body after it → no trailing `—` sentinel.
    assert format_doc_hit(hit) == "- [doc] docs/a.md:1-1 → Crumb"
