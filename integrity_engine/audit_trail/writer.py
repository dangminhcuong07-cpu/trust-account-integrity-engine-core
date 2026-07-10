"""
Audit trail writer — DB-to-file with explicit create vs sync semantics.

Extracted from obsidian_reporter._write_note() and phase3b_runner.sync_paper_trade_note().

The trading system had a subtle split that must be made explicit here:

  create_note()  — writes a new file; skips silently if file already exists.
                   (obsidian_reporter._write_note() behaviour)

  sync_note()    — always overwrites. DB is source of truth; the file is a
                   mirror. Called on every state change.
                   (sync_paper_trade_note() behaviour — it bypassed _write_note()
                   for exactly this reason)

Conflating these two modes was the root of the "sync is silently a no-op" bug
documented in phase3b_runner.py:275. They are separate methods here by design.

The output directory and file format are injected by the domain layer —
the writer is content-agnostic.
"""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import Protocol

from integrity_engine.core.types import AuditEntry


class ContentRenderer(Protocol):
    """Domain layer provides this to produce the file content for a given record."""

    def render(self, record_id: str, state: dict) -> str:
        """Return the full file content for the given record state."""
        ...


class AuditWriter:
    """
    Writes and syncs audit trail files for source records, and appends to
    an append-only audit log.

    Parameters
    ----------
    output_dir   Root directory where trail files are written.
    renderer     Domain-supplied callable that turns a record state into text.
                 Optional — required only for create_note / sync_note.
    dry_run      If True, print content instead of writing files.
    """

    def __init__(
        self,
        output_dir: Path,
        renderer: ContentRenderer | None = None,
        dry_run: bool = False,
    ) -> None:
        self._output_dir = output_dir
        self._renderer = renderer
        self._dry_run = dry_run

    def create_note(self, record_id: str, state: dict, relative_path: Path) -> bool:
        """
        Write a new audit note. Skips (returns False) if the file already exists.

        Use for initial creation. Never call this to update — use sync_note().
        In dry-run mode prints content and returns False without touching disk.
        """
        if self._renderer is None:
            raise ValueError("renderer is required for create_note — pass one to AuditWriter()")
        full_path = self._output_dir / relative_path

        if self._dry_run:
            content = self._renderer.render(record_id, state)
            sep = "=" * 60
            print(f"\n{sep}\nDRY-RUN — would create: {relative_path}\n{sep}\n{content}\n{sep}\n")
            return False

        if full_path.exists():
            return False

        full_path.parent.mkdir(parents=True, exist_ok=True)
        content = self._renderer.render(record_id, state)
        full_path.write_text(content, encoding="utf-8")
        return True

    def sync_note(self, record_id: str, state: dict, relative_path: Path) -> bool:
        """
        Overwrite the audit note with current state. Always writes.

        Call on every state change. DB is source of truth; this mirrors it.
        This is the invariant that Phase 3 Step 3.1 tests explicitly.
        In dry-run mode prints content and returns False without touching disk.
        """
        if self._renderer is None:
            raise ValueError("renderer is required for sync_note — pass one to AuditWriter()")
        full_path = self._output_dir / relative_path

        if self._dry_run:
            content = self._renderer.render(record_id, state)
            sep = "=" * 60
            print(f"\n{sep}\nDRY-RUN — would sync: {relative_path}\n{sep}\n{content}\n{sep}\n")
            return False

        full_path.parent.mkdir(parents=True, exist_ok=True)
        content = self._renderer.render(record_id, state)
        full_path.write_text(content, encoding="utf-8")
        return True

    def append_to_log(self, entry: AuditEntry, log_name: str = "audit.log") -> None:
        """
        Append one AuditEntry to the audit log file as a readable pipe-delimited line.

        The log is append-only. Each call adds one line:
            {wall_clock_timestamp} | {event_type} | {source_record_id} | {detail}

        The timestamp is always the wall-clock time at the moment of the call —
        not entry.timestamp — so the log records when each event actually occurred.
        In dry-run mode prints the line instead of writing to disk.
        """
        timestamp = datetime.datetime.now().isoformat()
        line = (
            f"{timestamp} | {entry.event_type} | "
            f"{entry.source_record_id} | {entry.detail}\n"
        )
        if self._dry_run:
            print(f"DRY-RUN audit.log: {line.rstrip()}")
            return
        log_path = self._output_dir / log_name
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as f:
            f.write(line)

    def record_state_change(
        self,
        record_id: str,
        state: dict,
        relative_path: Path,
        event_type: str = "STATE_CHANGED",
        detail: str = "",
    ) -> bool:
        """
        Record a state change atomically: syncs the note AND appends to the log.

        Calling sync_note alone leaves the log stale; calling append_to_log alone
        leaves the note file stale. Both must happen together — that is the invariant
        this method enforces. test_state_change_without_audit_write_fails_invariant
        guards it: remove either call here and the test fails.
        """
        synced = self.sync_note(record_id, state, relative_path)
        entry = AuditEntry(
            entry_id=f"{record_id}-{event_type}",
            source_record_id=record_id,
            event_type=event_type,
            timestamp="",   # append_to_log stamps with wall-clock time
            detail=detail,
        )
        self.append_to_log(entry)
        return synced
