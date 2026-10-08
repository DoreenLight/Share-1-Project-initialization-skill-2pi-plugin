#!/usr/bin/env python3
"""
verify_bundle.py - Complete Verification Utility for R-ICL Governance Bundles
Verifies:
  1. YAML frontmatter parsing and required fields by bundle type.
  2. State word separation protocol (6 canonical states + operational states).
  3. Validation Auditor closed verdict vocabulary (CONFORMANT, DEVIATIONS_FOUND, INCOMPLETE, OUT_OF_SCOPE).
  4. Cryptographic self-hash normalization rule (normalize_self_field_to_<SELF_HASH>_before_sha256).
  5. Sandbox allowlist write path boundary checks.
  6. CLI options to inspect, verify, compute hash, and stamp bundle_sha256 in-place.
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

# Canonical state vocabulary
CANONICAL_STATES = {
    "proposed",
    "approved",
    "implemented",
    "tested",
    "human-accepted",
    "scientifically-supported",
}

# Permissible operational/lifecycle states
LIFECYCLE_STATES = CANONICAL_STATES | {
    "ready",
    "claimed",
    "running",
    "submitted",
    "accepted",
    "blocked",
    "failed",
    "cancelled",
    "rejected",
    "superseded",
    "dispatched",
    "canonical-initialized",
    "active",
    "draft",
    "immutable",
    "recorded",
    "distilled",
    "archived",
    "deprecated",
}

# Closed validation verdicts
VALIDATION_VERDICTS = {
    "CONFORMANT",
    "DEVIATIONS_FOUND",
    "INCOMPLETE",
    "OUT_OF_SCOPE",
}

# Required fields per bundle type
REQUIRED_FIELDS = {
    "task-slice": ["task_slice_id", "revision", "status"],
    "handoff-bundle": ["handoff_id", "status", "sender", "intended_receiver"],
    "result-bundle": ["bundle_id", "status", "task_slice_ref", "worker"],
    "concept": ["id", "title", "status", "created"],
    "entity": ["id", "title", "status", "created"],
    "synthesis": ["id", "title", "status", "created"],
    "retro": ["id", "title", "status", "created"],
    "trajectory": ["id", "title", "status", "created"],
    "skill": ["id", "title", "status", "created"],
    "source": ["id", "title", "status", "created"],
}


def compute_raw_sha256(filepath: Path) -> str:
    """Compute raw SHA-256 hash of a file."""
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def normalize_bundle_content(content: str) -> str:
    """
    R-ICL bundle self-hash normalization rule:
    Replace `bundle_sha256: <anything>` in frontmatter with `bundle_sha256: <SELF_HASH>`.
    """
    return re.sub(r"(bundle_sha256\s*:\s*)([^\r\n]+)", r"\1<SELF_HASH>", content, count=1)


def compute_normalized_bundle_sha256(content: str) -> str:
    """Compute SHA-256 according to bundle_hash_rule."""
    norm = normalize_bundle_content(content)
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


def parse_frontmatter(content: str) -> tuple[dict[str, str], str]:
    """Robust frontmatter parser for markdown documents with fallback."""
    if not content.startswith("---"):
        return {}, content
    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}, content

    yaml_text = parts[1]
    body = parts[2]
    meta: dict[str, str] = {}

    # Try PyYAML if available for full fidelity
    try:
        import yaml  # type: ignore
        loaded = yaml.safe_load(yaml_text)
        if isinstance(loaded, dict):
            for k, v in loaded.items():
                meta[str(k)] = str(v) if v is not None else ""
            return meta, body
    except Exception:
        pass

    # Built-in zero-dependency parser
    for line in yaml_text.strip().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" in line:
            k, v = line.split(":", 1)
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if v.lower() == "null" or v == "~":
                v = ""
            meta[k] = v
    return meta, body


def stamp_bundle_hash(filepath: Path) -> str:
    """Stamp the calculated normalized self-hash directly into the bundle file."""
    if not filepath.exists():
        raise FileNotFoundError(f"File not found: {filepath}")

    content = filepath.read_text(encoding="utf-8")
    if not content.startswith("---"):
        raise ValueError("File does not contain YAML frontmatter")

    # If bundle_sha256 is not yet present in frontmatter, insert it before second ---
    if not re.search(r"bundle_sha256\s*:", content):
        parts = content.split("---", 2)
        yaml_part = parts[1].rstrip() + "\nbundle_sha256: <SELF_HASH>\n"
        content = f"---{yaml_part}---{parts[2]}"

    calc_sha = compute_normalized_bundle_sha256(content)
    stamped_content = re.sub(
        r"(bundle_sha256\s*:\s*)([^\r\n]+)",
        rf"\g<1>{calc_sha}",
        content,
        count=1,
    )
    filepath.write_text(stamped_content, encoding="utf-8")
    return calc_sha


def verify_bundle(filepath: Path, check_allowlist: bool = False, verbose: bool = True) -> bool:
    """
    Verify complete bundle integrity, fields, state vocabulary, verdicts, and hashes.
    Returns True if fully conformant, False otherwise.
    """
    if not filepath.exists():
        if verbose:
            print(f"[FAIL] File not found: {filepath}")
        return False

    content = filepath.read_text(encoding="utf-8")
    meta, body = parse_frontmatter(content)
    btype = meta.get("type", "UNKNOWN")
    status = meta.get("status", "UNKNOWN")

    if verbose:
        print(f"[*] Verifying bundle: {filepath.name}")
        print(f"    Type: {btype}")
        print(f"    Status: {status}")

    # 1. Required fields check
    req = REQUIRED_FIELDS.get(btype, ["type", "status"])
    missing = [f for f in req if f not in meta or meta[f] == ""]
    if missing:
        if verbose:
            print(f"    [FAIL] Missing required frontmatter fields: {missing}")
        return False

    # 2. State vocabulary check (unless template placeholder)
    if not status.startswith("{{") and status not in LIFECYCLE_STATES:
        if verbose:
            print(f"    [FAIL] Illegal status word '{status}'. Must be one of: {sorted(list(LIFECYCLE_STATES))}")
        return False

    # 3. Review verdict check
    bundle_type = meta.get("bundle_type", "")
    verdict = meta.get("verdict", "")
    if bundle_type == "review" or verdict:
        if not verdict:
            if verbose:
                print("    [FAIL] Validation ResultBundle must include 'verdict' field.")
            return False
        if verdict not in VALIDATION_VERDICTS:
            if verbose:
                print(f"    [FAIL] Illegal review verdict '{verdict}'. Must be one of: {sorted(list(VALIDATION_VERDICTS))}")
            return False
        if verbose:
            print(f"    [PASS] Validation review verdict valid: {verdict}")

    # 4. Cryptographic Hash Validation
    raw_sha = compute_raw_sha256(filepath)
    normalized_sha = compute_normalized_bundle_sha256(content)

    if verbose:
        print(f"    Raw file SHA-256:        {raw_sha}")
        print(f"    Normalized self-SHA-256: {normalized_sha}")

    declared_sha = meta.get("bundle_sha256", "").strip()
    if declared_sha:
        if declared_sha.startswith("{{") or declared_sha == "<SELF_HASH>":
            if verbose:
                print(f"    [INFO] File contains placeholder '{declared_sha}', skipping cryptographic hash equality.")
        else:
            if declared_sha == normalized_sha:
                if verbose:
                    print(f"    [PASS] Normalized self-hash matched perfectly: {declared_sha}")
            elif declared_sha == raw_sha:
                if verbose:
                    print(f"    [PASS] Raw file SHA-256 matched perfectly: {declared_sha}")
            else:
                if verbose:
                    print("    [FAIL] Cryptographic Hash Mismatch!")
                    print(f"      Declared in frontmatter: {declared_sha}")
                    print(f"      Calculated normalized:   {normalized_sha}")
                    print(f"      Calculated raw:          {raw_sha}")
                return False

    # 5. Path boundary checks
    if check_allowlist:
        forbidden_patterns = [
            r"\b00_入口/",
            r"\b01_需求与验收/",
            r"\b02_架构与合同/",
            r"\b03_实现/core/",
            r"\b07_运行记录/LOG\.md",
            r"\btemplates/",
            r"^\s*AGENTS\.md",
            r"^\s*README\.md",
            r"^\s*HANDOFF\.md",
        ]
        # Look for write paths declared in Outputs or actions
        lines = body.splitlines()
        in_write_section = False
        for line in lines:
            if "actual write paths" in line.lower() or "outputs" in line.lower():
                in_write_section = True
            elif line.startswith("## ") and in_write_section:
                in_write_section = False

            if in_write_section:
                for pat in forbidden_patterns:
                    if re.search(pat, line) and "workspaces/" not in line and "records/" not in line:
                        if verbose:
                            print(f"    [FAIL] Allowlist violation detected in body line: {line.strip()}")
                        return False

    if verbose:
        print("    [PASS] Bundle verification passed successfully.")
    return True


def main():
    parser = argparse.ArgumentParser(description="Verify and manage R-ICL governance bundle integrity.")
    parser.add_argument("file", help="Path to markdown bundle file")
    parser.add_argument("--check-allowlist", action="store_true", help="Enforce sandbox write path allowlist check")
    parser.add_argument("--compute-hash", action="store_true", help="Compute and display raw and normalized hashes")
    parser.add_argument("--stamp", action="store_true", help="Calculate and update bundle_sha256 in-place")

    args = parser.parse_args()
    target = Path(args.file)

    if args.compute_hash:
        if not target.exists():
            print(f"[FAIL] File not found: {target}")
            sys.exit(1)
        raw = compute_raw_sha256(target)
        norm = compute_normalized_bundle_sha256(target.read_text(encoding="utf-8"))
        print(f"File:            {target}")
        print(f"Normalized SHA:  {norm}")
        print(f"Raw file SHA:    {raw}")
        sys.exit(0)

    if args.stamp:
        try:
            stamped_sha = stamp_bundle_hash(target)
            print(f"[✔] Stamped bundle_sha256: {stamped_sha} in {target}")
            sys.exit(0)
        except Exception as e:
            print(f"[FAIL] Error stamping bundle: {e}")
            sys.exit(1)

    ok = verify_bundle(target, check_allowlist=args.check_allowlist, verbose=True)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
