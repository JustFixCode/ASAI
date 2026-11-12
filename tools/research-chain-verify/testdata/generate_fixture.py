"""Regenerate golden.jsonl using the production Python serializer; no network or execution."""
from pathlib import Path
import os
from research.ingestion import ResearchStore, capture_document

out = Path(__file__).with_name("golden.jsonl")
if out.exists():
    out.unlink()
store = ResearchStore(out)
for value in (
    {"schema_version": 1, "provenance": {"source_id": "fixture-1", "source_kind": "local_research_note", "source_label": "Fixture source", "source_reference": "paper-copy", "captured_at": "2026-01-02T03:04:05+00:00"}, "title": "ASCII fixture", "text": "First inert research note.\nNo instructions are executed."},
    {"schema_version": 1, "provenance": {"source_id": "fixture-2", "source_kind": "user_supplied_research", "source_label": "User material", "source_reference": "quoted-note", "captured_at": "2026-01-02T03:04:06.123456+00:00"}, "title": "Second fixture", "text": "Second inert note with a tab\tcharacter."},
):
    store.record(capture_document(value))
os.chmod(out, 0o600)
