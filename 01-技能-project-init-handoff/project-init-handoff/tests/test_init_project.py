#!/usr/bin/env python3
"""
test_init_project.py - Verification suite for project-init-handoff skill scripts & templates
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

# Add scripts directory to sys.path
import sys
SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

from init_project import init_decuple_project, get_decuple_dirs, AGILE_DIRS, compute_sha256
from verify_bundle import (
    verify_bundle,
    parse_frontmatter,
    compute_normalized_bundle_sha256,
    stamp_bundle_hash,
)
from log_event import append_event

R_ICL_PATH = Path("/Users/xbpd/Projects/R-ICL实验")


class TestProjectInitHandoff(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="test_project_init_")
        self.target_path = Path(self.temp_dir)
        self.resources_dir = SKILL_ROOT / "resources"

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_decuple_initialization_r_icl_profile(self):
        """Test full decuple directory structure, 12 templates, 4 schemas, and contracts."""
        init_decuple_project(
            target_dir=self.target_path,
            project_name="Test-R-ICL-System",
            author="Test-Agent",
            resources_dir=self.resources_dir,
            profile="r-icl",
            skip_contracts=False,
            dry_run=False,
        )

        # Check all decuple directories exist (profile r-icl uses 05_研究资产)
        dirs = get_decuple_dirs("r-icl")
        for d in dirs:
            dpath = self.target_path / d
            self.assertTrue(dpath.exists(), f"Directory should exist: {d}")
            self.assertTrue(dpath.is_dir(), f"Should be directory: {d}")

        # Check crucial baseline files exist
        crucial_files = [
            "AGENTS.md",
            "README.md",
            "HANDOFF.md",
            "00_入口/00_当前.md",
            "00_入口/01_路线图.md",
            "00_入口/02_决策记录.md",
            "00_入口/03_开放问题与风险.md",
            "07_运行记录/LOG.md",
            "01_需求与验收/05_Gate清单与批准边界.md",
            "01_需求与验收/07_错误处置与fail_closed.md",
            "02_架构与合同/01_实体与版本合同.md",
            "02_架构与合同/04_可执行不变量.md",
        ]
        for f in crucial_files:
            fpath = self.target_path / f
            self.assertTrue(fpath.exists(), f"Crucial file should exist: {f}")
            content = fpath.read_text(encoding="utf-8")
            self.assertGreater(len(content), 50, f"File {f} should have substantial content")

        # Check all 19 templates copied to templates/ (12 governance + 7 wiki templates)
        templates_dest = self.target_path / "templates"
        expected_templates = [
            "TaskSlice.md", "HandoffBundle.md", "ResultBundle.md",
            "TaskPackage.md", "ValidationReviewPackage.md", "Claim.md",
            "Decision.md", "EvidenceCard.md", "EvidenceSnapshot.md",
            "ExperimentSpec.md", "ResearchEvent.md", "RunManifest.md",
            "WikiConcept.md", "WikiEntity.md", "WikiSynthesis.md",
            "WikiRetro.md", "WikiTrajectory.md", "WikiSkillCase.md",
            "WikiSourcePacket.md",
        ]
        for t in expected_templates:
            self.assertTrue((templates_dest / t).exists(), f"Template {t} must exist in templates/")

        # Check templates directory does NOT contain root or non-template files
        self.assertFalse((templates_dest / "AGENTS.md").exists(), "AGENTS.md must NOT be in templates/")
        self.assertFalse((templates_dest / "HANDOFF.md").exists(), "HANDOFF.md must NOT be in templates/")
        self.assertFalse((templates_dest / "00_当前.md").exists(), "00_当前.md must NOT be in templates/")

        # Check all 5 schemas copied to 02_架构与合同/schemas/
        schemas_dest = self.target_path / "02_架构与合同" / "schemas"
        expected_schemas = [
            "task-slice.schema.json",
            "handoff-bundle.schema.json",
            "result-bundle.schema.json",
            "experiment-spec-readonly.schema.json",
            "wiki-page.schema.json",
        ]
        for s in expected_schemas:
            self.assertTrue((schemas_dest / s).exists(), f"Schema {s} must exist in schemas/")

        # Check wiki vault initialized in 05_研究资产/wiki
        wiki_root = self.target_path / "05_研究资产" / "wiki"
        self.assertTrue(wiki_root.exists())
        self.assertTrue((wiki_root / "meta" / "index.md").exists())
        self.assertTrue((wiki_root / "concepts").is_dir())
        self.assertTrue((wiki_root / "retro").is_dir())
        self.assertTrue((wiki_root / "skills").is_dir())

    def test_decuple_initialization_engineering_profile(self):
        """Test engineering profile initializes 05_资产库 and wiki."""
        init_decuple_project(
            target_dir=self.target_path,
            project_name="Engineering-Sys",
            author="Dev-Agent",
            resources_dir=self.resources_dir,
            profile="engineering",
            skip_contracts=False,
            dry_run=False,
        )
        self.assertTrue((self.target_path / "05_资产库").exists())
        self.assertTrue((self.target_path / "05_资产库" / "raw").exists())
        self.assertTrue((self.target_path / "05_资产库" / "wiki").exists())
        self.assertTrue((self.target_path / "05_资产库" / "wiki" / "meta" / "index.md").exists())

    def test_agile_initialization_structure(self):
        """Test agile mode directory creation and baselines."""
        agile_dir = self.target_path / "agile_proj"
        agile_dir.mkdir(parents=True, exist_ok=True)
        subprocess.run([
            sys.executable,
            str(SKILL_ROOT / "scripts" / "init_project.py"),
            "--target", str(agile_dir),
            "--mode", "agile",
        ], check=True)
        for d in AGILE_DIRS:
            self.assertTrue((agile_dir / d).exists(), f"Agile directory should exist: {d}")
        self.assertTrue((agile_dir / "AGENTS.md").exists())
        self.assertTrue((agile_dir / "HANDOFF.md").exists())
        self.assertTrue((agile_dir / "07_运行记录" / "LOG.md").exists())
        self.assertTrue((agile_dir / ".llm-wiki").exists(), ".llm-wiki must exist in agile mode")
        self.assertTrue((agile_dir / ".llm-wiki" / "meta" / "index.md").exists())

    def test_log_bootstrap_and_append_event(self):
        """Test initial LOG.md BOOTSTRAP and sequential append_event."""
        init_decuple_project(
            target_dir=self.target_path,
            project_name="Log-Test",
            author="Log-Agent",
            resources_dir=self.resources_dir,
            profile="r-icl",
            dry_run=False,
        )
        log_file = self.target_path / "07_运行记录" / "LOG.md"
        self.assertTrue(log_file.exists())
        content = log_file.read_text(encoding="utf-8")
        self.assertIn("PROC-0001", content)
        self.assertIn("BOOTSTRAP", content)

        # Append next event
        eid = append_event(
            log_path=log_file,
            event_type="DECISION",
            target_object="Q-001",
            change_desc="Approved scope",
            evidence="00_当前.md",
            next_step="Start TS-001",
        )
        self.assertEqual(eid, "PROC-0002")
        new_content = log_file.read_text(encoding="utf-8")
        self.assertIn("PROC-0002", new_content)
        self.assertIn("Approved scope", new_content)

        # Append wiki retro event
        eid3 = append_event(
            log_path=log_file,
            event_type="WIKI_RETRO",
            target_object="RETRO-20260914-0001",
            change_desc="Distilled atomic insight on CAS",
            evidence="05_研究资产/wiki/retro/RETRO-20260914-0001.md",
            next_step="Continue implementation",
        )
        self.assertEqual(eid3, "PROC-0003")
        self.assertIn("WIKI_RETRO", log_file.read_text(encoding="utf-8"))

        # Append wiki ensure-page and ingest events
        eid4 = append_event(
            log_path=log_file,
            event_type="WIKI_ENSURE_PAGE",
            target_object="CON-0001",
            change_desc="Ensured SSOT concept",
            evidence="05_研究资产/wiki/concepts/CON-0001.md",
            next_step="Ingest sources",
        )
        self.assertEqual(eid4, "PROC-0004")
        self.assertIn("WIKI_ENSURE_PAGE", log_file.read_text(encoding="utf-8"))

    def test_verify_real_r_icl_bundles(self):
        """Test verify_bundle on real physical bundles in R-ICL experiments."""
        if not R_ICL_PATH.exists():
            self.skipTest("R-ICL path not accessible")

        real_bundles = [
            R_ICL_PATH / "06_任务与交接/records/TS001-IMPL/attempt-001/HO-0001-TS001-IMPL@r1.md",
            R_ICL_PATH / "06_任务与交接/records/TS001-IMPL/attempt-001/RB-0001-TS001-IMPL@r1.md",
            R_ICL_PATH / "06_任务与交接/records/TS001-VAL/attempt-001/HO-0002-TS001-VAL@r1.md",
            R_ICL_PATH / "06_任务与交接/records/TS001-VAL/attempt-001/HO-0003-TS001-VAL@r1.md",
            R_ICL_PATH / "06_任务与交接/records/TS001-VAL/attempt-001/RB-0002-TS001-VAL@r1.md",
        ]
        for b in real_bundles:
            self.assertTrue(b.exists(), f"Bundle file must exist: {b}")
            ok = verify_bundle(b, verbose=False)
            self.assertTrue(ok, f"Real bundle should pass verification: {b.name}")

    def test_tampering_detection(self):
        """Test that altering a signed bundle fails closed."""
        src = R_ICL_PATH / "06_任务与交接/records/TS001-IMPL/attempt-001/HO-0001-TS001-IMPL@r1.md"
        if not src.exists():
            self.skipTest("R-ICL bundle not found")

        tampered_file = self.target_path / "tampered_ho.md"
        tampered_file.write_text(src.read_text(encoding="utf-8") + "\n# TAMPERED LINE", encoding="utf-8")
        ok = verify_bundle(tampered_file, verbose=False)
        self.assertFalse(ok, "Tampered bundle must fail cryptographic verification")

    def test_stamp_bundle_hash_utility(self):
        """Test that stamping a new bundle produces valid normalized self-hash."""
        test_file = self.target_path / "test_handoff.md"
        test_file.write_text("""---
type: handoff-bundle
handoff_id: HO-5555
status: dispatched
sender: Coordinator
intended_receiver: Worker
created: 2026-09-14
---
# Task Package
Execution instructions.
""", encoding="utf-8")
        stamped_sha = stamp_bundle_hash(test_file)
        self.assertEqual(len(stamped_sha), 64)
        ok = verify_bundle(test_file, verbose=False)
        self.assertTrue(ok, "Stamped bundle must pass verify_bundle")

    def test_state_word_validation(self):
        """Test that illegal status words fail validation."""
        bad_status_file = self.target_path / "bad_status.md"
        bad_status_file.write_text("""---
type: task-slice
task_slice_id: TS-001
revision: 1
status: random_unrecognized_status
---
# Content
""", encoding="utf-8")
        ok = verify_bundle(bad_status_file, verbose=False)
        self.assertFalse(ok, "Unrecognized status word must fail validation")

    def test_validation_verdict_vocabulary(self):
        """Test validation auditor verdict vocabulary enforcement."""
        bad_verdict_file = self.target_path / "bad_verdict.md"
        bad_verdict_file.write_text("""---
type: result-bundle
bundle_id: RB-0002
status: submitted
bundle_type: review
task_slice_ref: TS-001
worker: Auditor
verdict: PASSED_BY_AI
---
# Review
""", encoding="utf-8")
        self.assertFalse(verify_bundle(bad_verdict_file, verbose=False))

        good_verdict_file = self.target_path / "good_verdict.md"
        good_verdict_file.write_text("""---
type: result-bundle
bundle_id: RB-0002
status: submitted
bundle_type: review
task_slice_ref: TS-001
worker: Auditor
verdict: CONFORMANT
---
# Review
""", encoding="utf-8")
        self.assertTrue(verify_bundle(good_verdict_file, verbose=False))

    def test_allowlist_write_boundary(self):
        """Test that writing to forbidden canonical directories is caught by allowlist check."""
        violating_bundle = self.target_path / "violating_rb.md"
        violating_bundle.write_text("""---
type: result-bundle
bundle_id: RB-0001
status: submitted
task_slice_ref: TS-001
worker: Worker-Alpha
---
## Actions
- actual write paths: 03_实现/core/main.py
""", encoding="utf-8")
        ok = verify_bundle(violating_bundle, check_allowlist=True, verbose=False)
        self.assertFalse(ok, "Direct write to 03_实现/core/ must violate allowlist")


if __name__ == "__main__":
    unittest.main()
