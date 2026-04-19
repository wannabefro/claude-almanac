"""Local-only digest web UI.

Bound to 127.0.0.1:8787 by default. Templates and static assets live alongside
this module (`templates/`, `static/`) so they ship with the wheel via the
hatch force-include block in pyproject.toml.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from ..core import paths

PACKAGE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = PACKAGE_DIR / "templates"
STATIC_DIR = PACKAGE_DIR / "static"


def _digests_dir() -> Path:
    return paths.digests_dir()


def _activity_db() -> Path:
    return paths.data_dir() / "activity.db"


app = FastAPI(title="claude-almanac digest")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/health")
def health() -> JSONResponse:
    return JSONResponse({
        "digest_dir_ok": _digests_dir().is_dir(),
        "activity_db_ok": _activity_db().exists(),
        "claude_cli_ok": shutil.which("claude") is not None,
    })


def serve(
    *,
    host: str = "127.0.0.1",
    port: int | None = None,
) -> int:
    """Entry point used by `claude-almanac digest serve`."""
    import uvicorn

    port_int = port if port is not None else int(
        os.environ.get("CLAUDE_ALMANAC_DIGEST_PORT", "8787")
    )
    uvicorn.run(
        "claude_almanac.digest.server:app",
        host=host, port=port_int, reload=False, log_level="info",
    )
    return 0


import re as _re

from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

_DATE_RE = _re.compile(r"^\d{4}-\d{2}-\d{2}$")
_REPO_RE = _re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")


def _list_digests() -> dict:
    d = _digests_dir()
    if not d.is_dir():
        return {"daily": [], "by_repo": {}}
    daily: list[str] = []
    by_repo: dict[str, list[str]] = {}
    for p in d.glob("*.md"):
        stem = p.stem
        if _DATE_RE.match(stem):
            daily.append(stem)
            continue
        if len(stem) > 11 and stem[10] == "_" and _DATE_RE.match(stem[:10]):
            repo = stem[11:]
            if _REPO_RE.match(repo):
                by_repo.setdefault(repo, []).append(stem[:10])
    daily.sort()
    for v in by_repo.values():
        v.sort()
    return {"daily": daily, "by_repo": by_repo}


def _digest_file_for(date: str, repo: str | None) -> Path:
    name = f"{date}_{repo}.md" if repo else f"{date}.md"
    return _digests_dir() / name


def _validate_date_repo(date: str, repo: str | None) -> None:
    if not _DATE_RE.match(date):
        raise HTTPException(status_code=404, detail="invalid date format")
    if repo is not None and not _REPO_RE.match(repo):
        raise HTTPException(status_code=404, detail="invalid repo name")


def _latest_overall(listing: dict) -> tuple[str, str | None] | None:
    best: tuple[str, str | None] | None = None
    if listing["daily"]:
        best = (listing["daily"][-1], None)
    for repo, dates in listing["by_repo"].items():
        if not dates:
            continue
        candidate = (dates[-1], repo)
        if best is None or candidate[0] > best[0]:
            best = candidate
    return best


def _preview_text(markdown_body: str, max_chars: int = 240) -> str:
    buf: list[str] = []
    for line in markdown_body.splitlines():
        s = line.strip()
        if not s:
            if buf:
                break
            continue
        if s.startswith("#"):
            continue
        if s.startswith("-") or s.startswith("*"):
            s = s.lstrip("-* ").strip()
        buf.append(s)
        if sum(len(x) for x in buf) > max_chars:
            break
    text = " ".join(buf)
    for ch in ("`", "**", "__"):
        text = text.replace(ch, "")
    if len(text) > max_chars:
        text = text[: max_chars - 1].rsplit(" ", 1)[0] + "…"
    return text


def _recent_entries(listing: dict, limit: int = 5) -> list[dict]:
    entries: list[tuple[str, str | None]] = [
        (d, None) for d in listing["daily"]
    ]
    for repo, dates in listing["by_repo"].items():
        entries.extend((d, repo) for d in dates)
    entries.sort(key=lambda e: (e[0], e[1] or ""), reverse=True)
    return [
        {
            "date": date, "repo": repo,
            "url": f"/digest/{repo}/{date}" if repo else f"/digest/{date}",
        }
        for date, repo in entries[:limit]
    ]


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    listing = _list_digests()
    latest = _latest_overall(listing)
    preview = ""
    hero_url = hero_date = hero_repo = None
    if latest:
        hero_date, hero_repo = latest
        hero_url = (
            f"/digest/{hero_repo}/{hero_date}" if hero_repo
            else f"/digest/{hero_date}"
        )
        p = _digest_file_for(hero_date, hero_repo)
        if p.exists():
            preview = _preview_text(p.read_text())
    by_repo_latest = {
        repo: dates[-1]
        for repo, dates in sorted(listing["by_repo"].items())
        if dates
    }
    h = {
        "digest_dir_ok": _digests_dir().is_dir(),
        "activity_db_ok": _activity_db().exists(),
        "claude_cli_ok": shutil.which("claude") is not None,
    }
    h["ok"] = all(h.values())
    return templates.TemplateResponse(
        request, "home.html",
        {
            "hero": None if not latest else {
                "date": hero_date, "repo": hero_repo,
                "url": hero_url, "preview": preview,
            },
            "by_repo_latest": by_repo_latest,
            "recent": _recent_entries(listing, limit=5),
            "health": h,
            "total_daily": len(listing["daily"]),
            "total_repos": len(listing["by_repo"]),
        },
    )


@app.get("/today")
def today(request: Request):
    listing = _list_digests()
    latest = _latest_overall(listing)
    if latest is None:
        return RedirectResponse(url="/", status_code=307)
    date, repo = latest
    url = f"/digest/{repo}/{date}" if repo else f"/digest/{date}"
    return RedirectResponse(url=url, status_code=307)
