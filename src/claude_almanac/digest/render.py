"""Daily-digest markdown rendering + narrative shell-out.

Narratives are produced via the configured curator provider
(``cfg.digest.narrative_provider`` / ``cfg.digest.narrative_model``,
defaulting to ``cfg.curator`` if unset). Routes through
``curators.factory.make_curator`` so digest, rollups, and per-turn
curator all share the same provider surface.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from textwrap import dedent
from typing import Any

from claude_almanac.curators.base import Curator

LOGGER = logging.getLogger("claude_almanac.digest.render")


@dataclass
class DigestInputs:
    date: str
    window_hours: int
    new_memories: list[dict[str, Any]]
    retrievals: dict[str, int]
    commits_by_repo: dict[str, list[dict[str, Any]]]
    narratives_by_repo: dict[str, str]


def _fallback(commits: list[dict[str, Any]]) -> str:
    return "\n".join(f"- {c['sha'][:8]} {c['subject'].strip()}" for c in commits)


def haiku_narrate(
    *, repo: str, commits: list[dict[str, Any]], curator: Curator,
) -> str:
    """Summarise a day's commits as 2-3 bullets via the configured curator.

    Falls back to a bare sha+subject list if the curator returns nothing
    (empty string, error, or timeout — providers never raise per the
    Curator protocol).
    """
    if not commits:
        return "_no commits in window_"
    commits_text = "\n".join(
        f"- {c['sha'][:8]}  {c['subject']}  (by {c.get('author', '?')})"
        for c in commits
    )
    system_prompt = dedent("""
        You summarise a day's git commits into 2-3 markdown bullet points.
        Focus on what changed semantically, not individual commits. Do not
        invent details beyond what is given. Output ONLY the bullets, no
        preamble.
    """).strip()
    user_turn = dedent(f"""
        Repository: {repo}

        Commits:
        {commits_text}
    """).strip()
    try:
        result = curator.invoke(system_prompt, user_turn).strip()
    except Exception as e:
        LOGGER.warning("digest narrate: curator raised %s: %s", type(e).__name__, e)
        return _fallback(commits)
    if not result:
        return _fallback(commits)
    return result


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
