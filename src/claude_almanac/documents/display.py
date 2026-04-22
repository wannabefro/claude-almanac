"""Doc-hit display formatter (v0.4). Renders one hit as a markdown
bullet suitable for CLI output and UserPromptSubmit injection."""
from __future__ import annotations

from typing import Any


def format_doc_hit(hit: dict[str, Any], *, body_char_cap: int = 400) -> str:
    """Format as:
      - [doc] <file>:<line_start>-<line_end> -> <breadcrumb> - <first body line>

    breadcrumb is reconstructed from the text header line (line 1 of
    ``text`` under the ``// <file> [doc] <crumb>`` convention)."""
    text = hit.get("text") or ""
    if not isinstance(text, str):
        text = ""
    lines = text.splitlines()
    # Line 1 is "// <file> [doc] <breadcrumb>"
    crumb = ""
    if lines and lines[0].startswith("//"):
        after_tag = lines[0].split("[doc]", 1)
        if len(after_tag) == 2:
            crumb = after_tag[1].strip()
    body = "\n".join(lines[1:]).strip()
    first_body_line = body.splitlines()[0][:body_char_cap] if body else ""
    loc = f'{hit.get("file_path")}:{hit.get("line_start")}-{hit.get("line_end")}'
    return f"- [doc] {loc} → {crumb} — {first_body_line}"
