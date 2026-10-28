"""Deployment configs must run the web app as a single worker.

app.py keeps finished runs in an in-process dict (_RUNS). With more than one
gunicorn worker, the redirect to /results/<run_id> can reach a worker that never
saw the run and returns "Run not found" (reproduced: 6 of 30 requests with
--workers 2, 0 of 30 with --workers 1).
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _workers(text: str) -> list[int]:
    return [int(n) for n in re.findall(r"--workers[ =](\d+)", text)]


def test_render_runs_one_worker():
    assert _workers((ROOT / "render.yaml").read_text(encoding="utf-8")) == [1]


def test_dockerfile_runs_one_worker():
    dockerfile = ROOT / "Dockerfile"
    assert dockerfile.exists(), "Dockerfile missing"
    assert _workers(dockerfile.read_text(encoding="utf-8")) == [1]


def test_render_has_threads_so_one_run_does_not_block_others():
    # One worker is required (in-process _RUNS); threads keep a long pipeline
    # run from blocking every other request on the hosted demo.
    assert "--threads" in (ROOT / "render.yaml").read_text(encoding="utf-8")


def test_dockerfile_cmd_is_exec_form():
    # Shell-form CMD makes /bin/sh PID 1, which does not forward SIGTERM, so
    # `docker stop` and Ctrl+C waited 10s and then killed gunicorn.
    cmd = [l for l in (ROOT / "Dockerfile").read_text(encoding="utf-8").splitlines()
           if l.startswith("CMD")]
    assert cmd and cmd[0].startswith("CMD [") and "exec gunicorn" in cmd[0]


def test_dockerignore_keeps_private_paths_out_of_the_image():
    # Dockerfile does COPY . . ; these are git-ignored for a reason.
    ignored = (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
    for path in ("legal/", "outreach/", "docs/strategy/", ".env", ".env.*", "Velocity/"):
        assert path in ignored, path
