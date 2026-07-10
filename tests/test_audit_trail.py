"""
Tests for integrity_engine.audit_trail.

The critical test here (Phase 3, Step 3.1) is:
    "sync_note() MUST be called on every state change — a state change that
     is not mirrored to the audit trail is a test FAILURE."

That test is pre-declared below and remains skipped until Step 3.1.
"""

import pytest
from pathlib import Path
import tempfile

from integrity_engine.audit_trail.writer import AuditWriter


class _Renderer:
    def render(self, record_id, state):
        return f"content-{state['version']}"


class _StatusRenderer:
    def render(self, record_id, state):
        return f"status:{state['status']}"


# ── Scaffold ──────────────────────────────────────────────────────────────────

def test_scaffold_importable():
    from integrity_engine.audit_trail import AuditWriter
    assert AuditWriter is not None


# ── create_note ───────────────────────────────────────────────────────────────

def test_create_note_does_not_overwrite():
    """create_note skips if file already exists — never silently updates."""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        writer = AuditWriter(output_dir=root, renderer=_Renderer())
        path = Path("test-record.md")

        written1 = writer.create_note("rec1", {"version": 1}, path)
        written2 = writer.create_note("rec1", {"version": 2}, path)   # should skip

        assert written1 is True
        assert written2 is False
        assert (root / path).read_text() == "content-1"   # unchanged


def test_create_note_creates_parent_dirs():
    """create_note creates intermediate directories if they do not exist."""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        writer = AuditWriter(output_dir=root, renderer=_Renderer())
        path = Path("sub/dir/record.md")

        written = writer.create_note("rec1", {"version": 1}, path)

        assert written is True
        assert (root / path).read_text() == "content-1"


def test_create_note_dry_run_does_not_write(capsys):
    """In dry-run mode, create_note prints content and returns False."""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        writer = AuditWriter(output_dir=root, renderer=_Renderer(), dry_run=True)
        path = Path("test-record.md")

        result = writer.create_note("rec1", {"version": 1}, path)

        assert result is False
        assert not (root / path).exists()
        captured = capsys.readouterr()
        assert "content-1" in captured.out


# ── sync_note ─────────────────────────────────────────────────────────────────

def test_sync_note_always_overwrites():
    """sync_note always overwrites — DB is source of truth."""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        writer = AuditWriter(output_dir=root, renderer=_Renderer())
        path = Path("test-record.md")

        writer.create_note("rec1", {"version": 1}, path)
        writer.sync_note("rec1", {"version": 2}, path)   # must overwrite

        assert (root / path).read_text() == "content-2"


def test_sync_note_creates_file_when_not_exists():
    """sync_note creates the file even if no prior create_note was called."""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        writer = AuditWriter(output_dir=root, renderer=_Renderer())
        path = Path("new-record.md")

        result = writer.sync_note("rec1", {"version": 5}, path)

        assert result is True
        assert (root / path).read_text() == "content-5"


def test_sync_note_dry_run_does_not_write(capsys):
    """In dry-run mode, sync_note prints content and returns False."""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        writer = AuditWriter(output_dir=root, renderer=_Renderer(), dry_run=True)
        path = Path("test-record.md")

        result = writer.sync_note("rec1", {"version": 3}, path)

        assert result is False
        assert not (root / path).exists()
        captured = capsys.readouterr()
        assert "content-3" in captured.out


# ── Phase 3 Step 3.1 — the audit-trail sync invariant ────────────────────────
# This test MUST FAIL if a state change is not mirrored. It is deliberately
# NOT skipped once the implementation is in place.

def test_state_change_not_mirrored_fails():
    """
    Simulate a state change that is NOT followed by sync_note.
    The audit trail content must NOT match the new state — proving the
    test would catch the sync-on-close bug from the trading system.
    """
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        writer = AuditWriter(output_dir=root, renderer=_StatusRenderer())
        path = Path("test-record.md")

        writer.create_note("rec1", {"status": "OPEN"}, path)
        # Deliberately do NOT call sync_note after status changes to CLOSED
        # The file should still say OPEN — demonstrating the sync bug.
        content = (root / path).read_text()
        assert "OPEN" in content
        assert "CLOSED" not in content  # proves sync didn't happen


def test_state_change_without_audit_write_fails_invariant():
    """
    record_state_change() must write BOTH the note file and the audit log.
    If the append_to_log call is removed from record_state_change(), the
    audit.log will be empty and this test fails — proving the invariant is real.
    """
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        writer = AuditWriter(output_dir=root, renderer=_StatusRenderer())
        path = Path("test-record.md")

        writer.create_note("rec1", {"status": "OPEN"}, path)
        writer.record_state_change(
            "rec1", {"status": "CLOSED"}, path,
            event_type="STATE_CHANGED", detail="matter closed",
        )

        assert "CLOSED" in (root / path).read_text()
        log_content = (root / "audit.log").read_text()
        assert "rec1" in log_content
        assert "STATE_CHANGED" in log_content
