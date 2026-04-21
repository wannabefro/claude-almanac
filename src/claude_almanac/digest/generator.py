"""Daily-digest generator: collect → embed into activity.db → render → notify."""
from __future__ import annotations

import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from claude_almanac.core import archive, paths
from claude_almanac.core import config as core_config
from claude_almanac.curators.factory import make_curator
from claude_almanac.embedders import make_embedder

from . import notify as digest_notify
from .activity_db import CommitRecord, init_db, insert_commit, prune_activity
from .collectors import (
    collect_git_activity,
    collect_new_memories,
    collect_retrievals,
)
from .config import from_core_config
from .render import DigestInputs, haiku_narrate, render_digest

_REPO_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")


@dataclass
class GenerateResult:
    digest_path: str
    commits_inserted: int
    pruned: int
    notified: bool | None


def generate(
    *,
    cfg: core_config.Config | None = None,
    date: str | None = None,
    notify: bool = True,
    repo_filter: str | None = None,
    since_hours: int | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Run one generator pass. Returns a dict for CLI + web consumers."""
    if cfg is None:
        cfg = core_config.load()
    rt = from_core_config(cfg)

    if repo_filter is not None and not _REPO_RE.match(repo_filter):
        raise ValueError(
            f"invalid repo name {repo_filter!r}: must match {_REPO_RE.pattern}"
        )

    date = date or time.strftime("%Y-%m-%d", time.gmtime())
    window = since_hours if since_hours is not None else rt.window_hours
    cutoff_ts = time.time() - window * 3600
    cutoff_iso = time.strftime(
        "%Y-%m-%dT%H:%M:%SZ", time.gmtime(cutoff_ts),
    )

    embedder = make_embedder(cfg.embedder.provider, cfg.embedder.model)
    activity_db = Path(rt.activity_db)
    init_db(activity_db, embedder=embedder, model=cfg.embedder.model)

    new_memories = collect_new_memories(
        global_dir=str(paths.global_memory_dir()),
        projects_dir=str(paths.projects_memory_dir()),
        cutoff_ts=cutoff_ts,
    )
    retrievals = collect_retrievals(
        log_path=str(paths.logs_dir() / "retrieve.log"),
        cutoff_iso=cutoff_iso,
    )

    commits_by_repo: dict[str, list[dict[str, Any]]] = {}
    commits_inserted = 0
    for entry in rt.repos:
        if repo_filter and entry.name != repo_filter:
            continue
        commits = collect_git_activity(
            repo_path=entry.path, repo_name=entry.name, since_iso=cutoff_iso,
        )
        if not commits:
            continue
        commits_by_repo[entry.name] = [
            {"sha": c.sha, "subject": c.subject, "author": c.author}
            for c in commits
        ]
        if not dry_run:
            for c in commits:
                rec = CommitRecord(
                    repo=c.repo, sha=c.sha, author=c.author,
                    subject=c.subject, body=c.body,
                    stat_files=c.stat_files, stat_insertions=c.stat_insertions,
                    stat_deletions=c.stat_deletions,
                    diff_snippet=c.diff_snippet, committed_at=c.committed_at,
                )
                try:
                    if insert_commit(
                        activity_db, rec,
                        embedder=embedder, model=cfg.embedder.model,
                    ):
                        commits_inserted += 1
                except archive.EmbedderMismatch:
                    raise  # don't swallow — re-raise to abort the run
                except Exception as e:
                    print(
                        f"warn: insert failed for {c.repo}@{c.sha}: {e}",
                        file=sys.stderr,
                    )

    narrative_curator = make_curator(_digest_curator_cfg(cfg))
    narratives_by_repo = {
        repo: haiku_narrate(
            repo=repo, commits=commits, curator=narrative_curator,
        )
        for repo, commits in commits_by_repo.items()
    }

    md = render_digest(DigestInputs(
        date=date, window_hours=window,
        new_memories=new_memories, retrievals=retrievals,
        commits_by_repo=commits_by_repo,
        narratives_by_repo=narratives_by_repo,
    ))

    digest_dir = Path(rt.digest_dir)
    digest_dir.mkdir(parents=True, exist_ok=True)
    digest_path = digest_dir / (
        f"{date}_{repo_filter}.md" if repo_filter else f"{date}.md"
    )
    if dry_run:
        print(md)
    else:
        digest_path.write_text(md)

    pruned = (
        0 if dry_run
        else prune_activity(activity_db, retention_days=rt.retention_days)
    )

    notified: bool | None = None
    if notify and rt.notification and not dry_run:
        total_commits = sum(len(v) for v in commits_by_repo.values())
        title = (
            f"Daily digest · {len(commits_by_repo)} repos "
            f"· {len(new_memories)} new memories"
        )
        sub = f"{total_commits} commits · click to open"
        url = (
            f"http://127.0.0.1:8787/digest/{repo_filter}/{date}"
            if repo_filter
            else f"http://127.0.0.1:8787/digest/{date}"
        )
        notified = digest_notify.notify(title=title, message=sub, open_url=url)

    return {
        "digest_path": str(digest_path),
        "commits_inserted": commits_inserted,
        "pruned": pruned,
        "notified": notified,
    }


def _digest_curator_cfg(cfg: core_config.Config) -> core_config.Config:
    """Apply digest narrative provider/model overrides to cfg.curator.

    Mirrors the rollup runner's _override_curator pattern: an unset override
    (None) falls through to the existing curator config.
    """
    import dataclasses

    d = cfg.digest
    if d.narrative_provider is None and d.narrative_model is None:
        return cfg
    overrides: dict[str, Any] = {}
    if d.narrative_provider is not None:
        overrides["provider"] = d.narrative_provider
    if d.narrative_model is not None:
        overrides["model"] = d.narrative_model
    return dataclasses.replace(
        cfg, curator=dataclasses.replace(cfg.curator, **overrides),
    )
