"""Memory / retrieval-log / git-log collectors for the daily digest."""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


def _parse_frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---"):
        return {}
    end = text.find("---", 3)
    if end == -1:
        return {}
    fm: dict[str, str] = {}
    for line in text[3:end].splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            fm[k.strip()] = v.strip()
    return fm


def _scan_md_dir(base: Path, scope: str, cutoff_ts: float) -> list[dict]:
    if not base.exists():
        return []
    out: list[dict] = []
    for p in sorted(base.glob("*.md")):
        if p.name == "MEMORY.md":
            continue
        st = p.stat()
        if st.st_mtime < cutoff_ts:
            continue
        fm = _parse_frontmatter(p.read_text(errors="replace"))
        out.append({
            "scope": scope,
            "slug": p.stem,
            "kind": fm.get("type", "unknown"),
            "name": fm.get("name", p.stem),
            "description": fm.get("description", ""),
            "path": str(p),
            "mtime": st.st_mtime,
        })
    return out


def collect_new_memories(
    *,
    global_dir: str,
    projects_dir: str,
    cutoff_ts: float,
) -> list[dict]:
    results: list[dict] = []
    results.extend(_scan_md_dir(Path(global_dir), "global", cutoff_ts))
    projects_root = Path(projects_dir)
    if projects_root.is_dir():
        for entry in sorted(projects_root.iterdir()):
            if entry.is_dir():
                results.extend(_scan_md_dir(entry, entry.name, cutoff_ts))
    return results


_KV_FIELD = re.compile(r"(\w+)=(\S+)")


def _parse_log_line(raw: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for key, val in _KV_FIELD.findall(raw):
        if val.startswith('"') and val.endswith('"'):
            val = (
                val[1:-1]
                .replace('\\"', '"')
                .replace("\\t", "\t")
                .replace("\\n", "\n")
                .replace("\\r", "\r")
                .replace("\\\\", "\\")
            )
        fields[key] = val
    return fields


def collect_retrievals(*, log_path: str, cutoff_iso: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    p = Path(log_path)
    if not p.exists():
        return counts
    for raw in p.read_text(errors="replace").splitlines():
        fields = _parse_log_line(raw)
        if fields.get("event") != "memory.injected":
            continue
        ts = fields.get("ts", "")
        if not ts or ts < cutoff_iso:
            continue
        sources = fields.get("sources", "")
        for src in sources.split(","):
            src = src.strip()
            if src:
                counts[src] = counts.get(src, 0) + 1
    return counts


@dataclass
class GitCommit:
    repo: str
    sha: str
    subject: str
    body: str
    author: str
    committed_at: str
    stat_files: int
    stat_insertions: int
    stat_deletions: int
    diff_snippet: str


def _git(repo_path: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=repo_path, capture_output=True, text=True,
        timeout=30, check=False,
    )


def _is_git_repo(path: str) -> bool:
    if not Path(path).is_dir():
        return False
    out = _git(path, "rev-parse", "--git-dir")
    return out.returncode == 0


def _commit_stats(repo_path: str, sha: str) -> tuple[int, int, int, str]:
    show = _git(repo_path, "show", "--stat", "--format=", sha)
    files = insertions = deletions = 0
    if show.returncode == 0:
        lines_out = show.stdout.rstrip().splitlines()
        last = lines_out[-1] if lines_out else ""
        m = re.search(
            r"(\d+)\s+files?\s+changed"
            r"(?:,\s+(\d+)\s+insertions?\(\+\))?"
            r"(?:,\s+(\d+)\s+deletions?\(-\))?",
            last,
        )
        if m:
            files = int(m.group(1))
            insertions = int(m.group(2) or 0)
            deletions = int(m.group(3) or 0)
    diff = _git(repo_path, "show", "--format=", "--no-color", sha)
    snippet = diff.stdout[:2048] if diff.returncode == 0 else ""
    return files, insertions, deletions, snippet


def collect_git_activity(
    *, repo_path: str, repo_name: str, since_iso: str,
) -> list[GitCommit]:
    if not _is_git_repo(repo_path):
        return []
    fmt = "%H%x1f%s%x1f%b%x1f%an%x1f%cI"
    log = _git(
        repo_path, "log",
        f"--since={since_iso}",
        f"--pretty=format:{fmt}%x1e",
    )
    if log.returncode != 0 or not log.stdout:
        return []
    commits: list[GitCommit] = []
    for record in log.stdout.split("\x1e"):
        record = record.strip("\n")
        if not record:
            continue
        fields = record.split("\x1f", maxsplit=4)
        if len(fields) < 5:
            continue
        sha, subject, body, author, committed_at = fields[:5]
        stat_files, ins, dels, snippet = _commit_stats(repo_path, sha)
        commits.append(GitCommit(
            repo=repo_name, sha=sha, subject=subject, body=body,
            author=author, committed_at=committed_at,
            stat_files=stat_files, stat_insertions=ins, stat_deletions=dels,
            diff_snippet=snippet,
        ))
    return commits
