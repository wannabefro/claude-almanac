"""Daily-digest markdown rendering + Haiku narrative shell-out."""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from textwrap import dedent
from typing import Any


@dataclass
class DigestInputs:
    date: str
    window_hours: int
    new_memories: list[dict[str, Any]]
    retrievals: dict[str, int]
    commits_by_repo: dict[str, list[dict[str, Any]]]
    narratives_by_repo: dict[str, str]


def _call_claude_cli(argv: list[str], stdin: str) -> str:
    try:
        out = subprocess.run(
            argv, input=stdin, capture_output=True, text=True,
            timeout=60, check=False,
        )
    except FileNotFoundError as e:
        raise RuntimeError(f"claude CLI missing: {e}") from e
    if out.returncode != 0:
        raise RuntimeError(f"claude exit {out.returncode}: {out.stderr[:400]}")
    return out.stdout.strip()


def haiku_narrate(*, repo: str, commits: list[dict[str, Any]], model: str) -> str:
    if not commits:
        return "_no commits in window_"
    commits_text = "\n".join(
        f"- {c['sha'][:8]}  {c['subject']}  (by {c.get('author', '?')})"
        for c in commits
    )
    prompt = dedent(f"""
        Summarize this day's commits in {repo} as 2-3 bullet points (markdown).
        Focus on what changed semantically, not individual commits.
        Do not invent details beyond what is given.

        Commits:
        {commits_text}
    """).strip()
    try:
        return _call_claude_cli(["claude", "-p", "--model", model], stdin=prompt)
    except (RuntimeError, FileNotFoundError):
        return "\n".join(
            f"- {c['sha'][:8]} {c['subject'].strip()}" for c in commits
        )


def render_digest(inputs: DigestInputs) -> str:
    lines: list[str] = []
    lines.append(f"# Daily digest — {inputs.date}")
    lines.append("")
    lines.append(f"_Window: last {inputs.window_hours} hours_")
    lines.append("")
    lines.append("## New memories")
    lines.append("")
    if not inputs.new_memories:
        lines.append("_no new memories_")
    else:
        for m in inputs.new_memories:
            desc = f" — {m['description']}" if m.get("description") else ""
            lines.append(
                f"- **[{m['kind']}]** `{m['slug']}` "
                f"(scope: {m['scope']}){desc}"
            )
    lines.append("")
    lines.append("## Frequently surfaced")
    lines.append("")
    if not inputs.retrievals:
        lines.append("_no retrievals recorded in window_")
    else:
        for src, count in sorted(
            inputs.retrievals.items(), key=lambda kv: -kv[1]
        ):
            lines.append(f"- `{src}` — surfaced {count}×")
    lines.append("")
    lines.append("## Repo activity")
    lines.append("")
    if not inputs.commits_by_repo:
        lines.append("_no activity_")
        lines.append("")
    else:
        for repo, commits in sorted(inputs.commits_by_repo.items()):
            lines.append(f"### {repo}")
            lines.append("")
            narrative = inputs.narratives_by_repo.get(repo, "")
            if narrative:
                lines.append(narrative)
            else:
                for c in commits:
                    lines.append(f"- {c['sha'][:8]} {c['subject']}")
            lines.append("")
    total_commits = sum(len(v) for v in inputs.commits_by_repo.values())
    lines.append("## Totals")
    lines.append("")
    lines.append(f"- {len(inputs.new_memories)} new memories")
    lines.append(f"- {len(inputs.retrievals)} distinct memories surfaced")
    lines.append(
        f"- {total_commits} commits across "
        f"{len(inputs.commits_by_repo)} repos"
    )
    lines.append("")
    return "\n".join(lines)
