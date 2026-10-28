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
