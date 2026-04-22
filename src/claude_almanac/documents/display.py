"""Doc-hit display formatter (v0.4). Renders one hit as a markdown
bullet suitable for CLI output and UserPromptSubmit injection."""
from __future__ import annotations

from typing import Any


def format_doc_hit(hit: dict[str, Any], *, body_char_cap: int = 400) -> str:
    """Format as one of:
      - ``- [doc] <loc> → <crumb> — <first body line>`` (both present)
      - ``- [doc] <loc> → <crumb>``                    (crumb only)
      - ``- [doc] <loc> — <first body line>``          (body only)
      - ``- [doc] <loc>``                              (neither)

    breadcrumb is reconstructed from the text header line (line 1 of
    ``text`` under the ``// <file> [doc] <crumb>`` convention). Empty
    sentinels are elided so CLI output doesn't carry trailing ``→`` /
    ``—`` noise when the fixture lacks a header or body."""
    text = hit.get("text") or ""
    if not isinstance(text, str):
        text = ""
    lines = text.splitlines()
    # Line 1 is "// <file> [doc] <breadcrumb>" when the chunk was ingested
    # through the doc extractor. If the header is absent, don't eat line 0
    # — it's the first line of the body itself.
    crumb = ""
    has_header = bool(lines) and lines[0].startswith("//")
    if has_header:
        after_tag = lines[0].split("[doc]", 1)
        if len(after_tag) == 2:
            crumb = after_tag[1].strip()
    body_lines = lines[1:] if has_header else lines
    body = "\n".join(body_lines).strip()
    first_body_line = body.splitlines()[0][:body_char_cap] if body else ""
    loc = f'{hit.get("file_path")}:{hit.get("line_start")}-{hit.get("line_end")}'
    head = f"- [doc] {loc}"
    if crumb and first_body_line:
        return f"{head} → {crumb} — {first_body_line}"
    if crumb:
        return f"{head} → {crumb}"
    if first_body_line:
        return f"{head} — {first_body_line}"
    return head
