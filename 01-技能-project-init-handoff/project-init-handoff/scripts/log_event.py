#!/usr/bin/env python3
"""
log_event.py - Append-Only Process Logger for 07_运行记录/LOG.md
Guarantees:
  1. Append-only integrity: never overwrites or alters existing event rows.
  2. Automatic sequential event numbering: PROC-0001, PROC-0002, etc.
  3. Clean markdown table formatting.
  4. Automatic update of frontmatter 'updated' date.
"""
from __future__ import annotations

import argparse
import datetime
import re
import sys
from pathlib import Path

VALID_EVENT_TYPES = {
    "BOOTSTRAP",
    "DECISION",
    "DRAFT_CREATED",
    "APPROVAL",
    "PACKAGE_DISPATCHED",
    "CORRECTION",
    "STATE_TRANSITION",
    "CANDIDATE_HANDOFF",
    "COORD_ACCEPT",
    "VERIFICATION",
    "PROMOTION",
    "CANONICAL_BOOTSTRAP",
    "FAIL_CLOSED_REFUSAL",
    "WIKI_INIT",
    "WIKI_INGEST",
    "WIKI_ENSURE_PAGE",
    "WIKI_RETRO",
    "WIKI_OBSERVE",
    "WIKI_TRAJECTORY",
    "WIKI_DISTILL",
    "WIKI_LINT",
    "WIKI_REBUILD",
}


def append_event(
    log_path: Path,
    event_type: str,
    target_object: str,
    change_desc: str,
    evidence: str,
    next_step: str,
    date_str: str | None = None,
) -> str:
    if not log_path.exists():
        raise FileNotFoundError(f"LOG file not found: {log_path}")

    content = log_path.read_text(encoding="utf-8")
    today = date_str or datetime.date.today().isoformat()

    # Find highest existing PROC-XXXX
    existing_nums = [int(m) for m in re.findall(r"PROC-(\d{4})", content)]
    next_num = max(existing_nums) + 1 if existing_nums else 1
    event_id = f"PROC-{next_num:04d}"

    # Construct table row
    # Escaping pipes in cell contents
    def clean(s: str) -> str:
        return s.replace("|", "\\|").strip()

    row = f"| {event_id} | {today} | {clean(event_type)} | {clean(target_object)} | {clean(change_desc)} | {clean(evidence)} | {clean(next_step)} |\n"

    # Update frontmatter 'updated' date
    updated_content = re.sub(r"(updated:\s*)\S+", rf"\g<1>{today}", content, count=1)

    # Ensure trailing newline before append
    if not updated_content.endswith("\n"):
        updated_content += "\n"

    final_content = updated_content + row
    log_path.write_text(final_content, encoding="utf-8")
    return event_id


def main():
    parser = argparse.ArgumentParser(description="Append an event to 07_运行记录/LOG.md")
    parser.add_argument("--log", "-l", required=True, help="Path to 07_运行记录/LOG.md")
    parser.add_argument("--type", "-t", required=True, help=f"Event type, e.g. {', '.join(sorted(list(VALID_EVENT_TYPES)))}")
    parser.add_argument("--object", "-o", required=True, help="Subject object, e.g. 'TS-001' or 'Q-001'")
    parser.add_argument("--change", "-c", required=True, help="Description of the change or action")
    parser.add_argument("--evidence", "-e", required=True, help="Evidence path or reference")
    parser.add_argument("--next", "-n", required=True, help="Next immediate action")

    args = parser.parse_args()
    log_path = Path(args.log).resolve()

    try:
        eid = append_event(
            log_path=log_path,
            event_type=args.type,
            target_object=args.object,
            change_desc=args.change,
            evidence=args.evidence,
            next_step=args.next,
        )
        print(f"[✔] Appended event {eid} to {log_path}")
    except Exception as err:
        print(f"[FAIL] Error appending event: {err}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
