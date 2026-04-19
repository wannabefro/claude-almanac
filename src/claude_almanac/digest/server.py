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
