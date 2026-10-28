"""Deployment configs must run the web app as a single worker.

app.py keeps finished runs in an in-process dict (_RUNS). With more than one
gunicorn worker, the redirect to /results/<run_id> can reach a worker that never
saw the run and returns "Run not found" (reproduced: 6 of 30 requests with
--workers 2, 0 of 30 with --workers 1).
"""
from __future__ import annotations

import re
from fnmatch import fnmatch
from pathlib import Path

from tests.test_docs_match_code import DOCS_WITH_RULE_TABLES

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


PRIVATE_EXAMPLES = [
    # Dockerfile does COPY . . ; these exist in the owner's working folder and are git-ignored.
    "legal/engagement.docx", "outreach/emails.md", "docs/strategy/plan.md",
    "docs/trustsentry-lawyer-briefing.md", "docs/superpowers/x.md", ".env", ".env.local",
    "Velocity/entry.pdf", "CLIENT-Proposal-TrustLedger-Monitoring.md",
    "FOUNDER-Build-and-Prep-Plan.md", "pitch[to firms]/deck.pptx", "archive of suggestions/a.md",
    "trust-account-integrity-engine/node_modules/react/index.js", ".worktrees/x/app.py",
    "venv/Lib/site.py", "build/app.exe", "dist/app.exe", "output/coastal_law/evidence_pack.md",
    "some-new-private-file.md",
]


def test_dockerignore_keeps_private_paths_out_of_the_image():
    leaked = [p for p in PRIVATE_EXAMPLES if not _dockerignored(p)]
    assert not leaked, f"would be copied into the image: {leaked}"


def _dockerignored(path: str) -> bool:
    """Last matching .dockerignore pattern wins; '!' re-includes; a pattern also covers everything below it."""
    ignored = False
    for line in (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        negate = line.startswith("!")
        pattern = line.lstrip("!").rstrip("/")
        parts = path.split("/")
        prefixes = ["/".join(parts[:i]) for i in range(1, len(parts) + 1)]
        if any(fnmatch(p, pattern) for p in prefixes):
            ignored = not negate
    return ignored


def test_files_the_image_needs_are_not_dockerignored():
    # .claude was dockerignored while test_docs_match_code read .claude/CLAUDE.md,
    # so `docker run ... pytest` failed in the image but passed locally and in CI.
    needed = [*DOCS_WITH_RULE_TABLES, "app.py", "run.py", "requirements.txt", "Dockerfile",
              "render.yaml", ".dockerignore", "trust_domain/rules/__init__.py",
              "trust_domain/config/coastal_law.toml", "integrity_engine/__init__.py",
              "replay/engine.py", "tests/test_deploy_config.py", "data/sample/client_ledger.csv"]
    missing = [p for p in needed if _dockerignored(p)]
    assert not missing, f"excluded from the image by .dockerignore: {missing}"
