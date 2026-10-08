#!/usr/bin/env python3
"""
test_wiki_tool.py - Test suite for LLM Wiki Knowledge Compounding & Agent Memory Engine
"""
from __future__ import annotations

import datetime
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

# Add scripts directory to sys.path
SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

from wiki_tool import (
    init_vault,
    capture_source,
    record_retro,
    record_trajectory,
    distill_skill,
    append_observation,
    ensure_page,
    ingest_sources,
    search_registry,
    print_watch_schedule,
    layered_recall,
    rebuild_metadata,
    lint_vault,
    scan_vault_pages,
    parse_frontmatter,
    dump_frontmatter,
    compute_content_sha256,
    clean_and_extract_links,
    resolve_project_vault,
    log_vault_event,
)


class TestWikiTool(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="test_wiki_tool_")
        self.vault_path = Path(self.temp_dir) / "project_wiki"
        self.personal_vault_path = Path(self.temp_dir) / "personal_wiki"

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_init_vault(self):
        """Test vault initialization creates required subdirs and baseline metadata."""
        init_vault(self.vault_path, is_personal=False)
        for sub in [
            "concepts", "entities", "synthesis", "retro",
            "trajectories", "skills", "sources", "meta"
        ]:
            self.assertTrue((self.vault_path / sub).is_dir(), f"Subdir {sub} must exist")

        self.assertTrue((self.vault_path / "README.md").exists())
        self.assertTrue((self.vault_path / "meta" / "index.md").exists())
        self.assertTrue((self.vault_path / "meta" / "observations.md").exists())
        self.assertTrue((self.vault_path / "meta" / "backlinks.json").exists())
        self.assertTrue((self.vault_path / "meta" / "registry.json").exists())

    def test_capture_source(self):
        """Test capturing immutable source packet with SHA-256."""
        init_vault(self.vault_path)
        sample_file = Path(self.temp_dir) / "sample_source.txt"
        sample_file.write_text("Hello Karpathy LLM Wiki Architecture\nDeterministic Knowledge\n", encoding="utf-8")

        dest = capture_source(
            vault=self.vault_path,
            title="Sample Source Document",
            source_location=str(sample_file),
            content=sample_file.read_text(encoding="utf-8"),
            source_type="file",
            tags=["sample", "karpathy"],
            summary="A test source document for verification.",
        )

        self.assertTrue(dest.exists())
        meta, body = parse_frontmatter(dest.read_text(encoding="utf-8"))
        self.assertEqual(meta.get("type"), "source")
        self.assertEqual(meta.get("status"), "immutable")
        self.assertEqual(meta.get("source_type"), "file")
        self.assertIn("source_sha256", meta)
        expected_sha = compute_content_sha256(sample_file.read_text(encoding="utf-8"))
        self.assertEqual(meta.get("source_sha256"), expected_sha)
        self.assertIn("Hello Karpathy LLM Wiki Architecture", body)

    def test_record_retro(self):
        """Test recording atomic insight post-task retrospective."""
        init_vault(self.vault_path)
        dest = record_retro(
            vault=self.vault_path,
            title="Always Use Compare-and-Swap in State Mutations",
            insight="Directly overwriting state leads to silent race conditions. Always specify expected_version.",
            task_slice="TS001-IMPL",
            context="Attempt 1 collided with background reconciler.",
            tags=["cas", "concurrency", "governance"],
            summary="Atomic insight on avoiding race conditions.",
        )

        self.assertTrue(dest.exists())
        meta, body = parse_frontmatter(dest.read_text(encoding="utf-8"))
        self.assertEqual(meta.get("type"), "retro")
        self.assertEqual(meta.get("task_slice_ref"), "TS001-IMPL")
        self.assertIn("concurrency", meta.get("tags", []))
        self.assertIn("Compare-and-Swap", body)

    def test_record_trajectory_and_distill_skill(self):
        """Test recording agent problem-solving trajectory and distilling into reusable skill."""
        init_vault(self.vault_path)

        # 1. Record Trajectory
        traj_dest = record_trajectory(
            vault=self.vault_path,
            title="Resolving Sandbox Path Access Violations",
            objective="Grant restricted write access to attempt workspace only.",
            steps="Step 1: Inspect allowlist.\nStep 2: Detect illegal root write attempt.\nStep 3: Redirect to workspace.",
            task_slice="TS002-IMPL",
            bottlenecks="Worker attempted to touch root README.md directly.",
            breakthrough="Constrained write hook strictly to 03_实现/workspaces/.",
            outcome="Passes INV-007 validation.",
            tags=["sandbox", "security", "trajectory"],
        )
        self.assertTrue(traj_dest.exists())
        traj_meta, _ = parse_frontmatter(traj_dest.read_text(encoding="utf-8"))
        traj_id = traj_meta["id"]
        self.assertEqual(traj_meta["status"], "recorded")

        # 2. Distill Skill
        skill_dest = distill_skill(
            vault=self.vault_path,
            title="Safe Sandbox Workspace Configuration Playbook",
            pattern="1. Read allowlist\n2. Configure output paths strictly inside workspace\n3. Pre-check write targets",
            trajectories=[traj_id],
            antipatterns="Do not grant wildcards or root access.",
            checklist=["Path in workspace", "Hash matches", "INV-007 passes"],
            tags=["security", "playbook"],
            summary="Universal procedure for safe agent workspace isolation.",
        )
        self.assertTrue(skill_dest.exists())
        skill_meta, skill_body = parse_frontmatter(skill_dest.read_text(encoding="utf-8"))
        self.assertEqual(skill_meta["type"], "skill")
        self.assertIn(traj_id, skill_meta["trajectories"])
        self.assertIn("Safe Sandbox", skill_body)

        # 3. Check trajectory status was updated to distilled
        updated_traj_meta, _ = parse_frontmatter(traj_dest.read_text(encoding="utf-8"))
        self.assertEqual(updated_traj_meta["status"], "distilled")

    def test_append_observation(self):
        """Test appending timestamped session observations."""
        init_vault(self.vault_path)
        append_observation(
            vault=self.vault_path,
            text="Detected python 3.12 syntax warning in legacy regex parser.",
            author="Auditor-VAL",
            tags=["python3.12", "warning"],
        )
        obs_content = (self.vault_path / "meta" / "observations.md").read_text(encoding="utf-8")
        self.assertIn("Auditor-VAL", obs_content)
        self.assertIn("python 3.12 syntax warning", obs_content)
        self.assertIn("#python3.12", obs_content)

    def test_rebuild_metadata_and_backlinks(self):
        """Test deterministic rebuild of index.md, backlinks graph, and registry."""
        init_vault(self.vault_path)

        # Create Concept A
        concept_a = self.vault_path / "concepts" / "CON-0001.md"
        concept_a.write_text("""---
id: CON-0001
title: "单事实源 (Single Source of Truth)"
type: concept
status: active
created: 2026-09-14
tags: [architecture]
summary: "权威当前状态准则。"
---
# 单事实源
核心准则。
""", encoding="utf-8")

        # Create Concept B referencing Concept A
        concept_b = self.vault_path / "concepts" / "CON-0002.md"
        concept_b.write_text("""---
id: CON-0002
title: "两阶段交付 (Two-Phase Promotion)"
type: concept
status: active
created: 2026-09-14
tags: [governance]
summary: "候选交付与正式入库分离。"
---
# 两阶段交付
依赖 [[CON-0001|单事实源]] 进行状态跃迁。
""", encoding="utf-8")

        rebuild_metadata(self.vault_path)

        # Check meta/index.md
        index_text = (self.vault_path / "meta" / "index.md").read_text(encoding="utf-8")
        self.assertIn("CON-0001", index_text)
        self.assertIn("CON-0002", index_text)
        self.assertIn("单事实源", index_text)
        self.assertIn("两阶段交付", index_text)

        # Check backlinks.json
        backlinks_data = json.loads((self.vault_path / "meta" / "backlinks.json").read_text(encoding="utf-8"))
        self.assertIn("concepts/CON-0001.md", backlinks_data)
        self.assertIn("concepts/CON-0002.md", backlinks_data["concepts/CON-0001.md"])

        # Check registry.json
        reg_data = json.loads((self.vault_path / "meta" / "registry.json").read_text(encoding="utf-8"))
        self.assertIn("CON-0001", reg_data)
        self.assertEqual(reg_data["CON-0001"]["title"], "单事实源 (Single Source of Truth)")
        self.assertEqual(reg_data["CON-0001"]["inbound_links_count"], 1)

    def test_lint_vault_detection_and_autofix(self):
        """Test mechanical linting detects broken links, orphans, frontmatter errors and auto-fixes unindexed pages."""
        init_vault(self.vault_path)

        # 1. Create a page with broken link
        broken_page = self.vault_path / "concepts" / "CON-0099.md"
        broken_page.write_text("""---
id: CON-0099
title: "Broken Link Test"
type: concept
status: active
created: 2026-09-14
---
Links to nonexistent [[concepts/NONEXISTENT_PAGE]].
""", encoding="utf-8")

        # 2. Create a page with missing required frontmatter
        bad_meta_page = self.vault_path / "concepts" / "CON-BAD.md"
        bad_meta_page.write_text("""---
title: "Missing Fields"
---
No id, type, status, or created.
""", encoding="utf-8")

        report = lint_vault(self.vault_path, auto_fix=False)
        self.assertFalse(report["passed"])
        self.assertGreaterEqual(len(report["broken_links"]), 1)
        self.assertTrue(any(b["target"] == "concepts/NONEXISTENT_PAGE" for b in report["broken_links"]))
        self.assertTrue(any("Missing required frontmatter fields" in e["error"] for e in report["frontmatter_errors"]))

        # Remove the invalid files and verify clean lint
        broken_page.unlink()
        bad_meta_page.unlink()

        # Create valid page
        valid_page = self.vault_path / "concepts" / "CON-0010.md"
        valid_page.write_text("""---
id: CON-0010
title: "Valid Concept"
type: concept
status: active
created: 2026-09-14
summary: "Clean test."
---
# Valid Concept
Links to [[meta/index]].
""", encoding="utf-8")

        # First without auto-fix: page is unindexed
        report2 = lint_vault(self.vault_path, auto_fix=False)
        self.assertIn("concepts/CON-0010.md", report2["unindexed_pages"])

        # Run with auto_fix=True: automatically rebuilds metadata index
        report3 = lint_vault(self.vault_path, auto_fix=True)
        self.assertEqual(len(report3["unindexed_pages"]), 0)
        self.assertEqual(len(report3["broken_links"]), 0)
        self.assertEqual(len(report3["frontmatter_errors"]), 0)
        self.assertTrue(report3["passed"])

    def test_layered_recall(self):
        """Test layered recall searches both project and personal vaults with proper tagging."""
        init_vault(self.vault_path)
        init_vault(self.personal_vault_path, is_personal=True)

        # Add project page
        (self.vault_path / "concepts" / "CON-0001.md").write_text("""---
id: CON-0001
title: "Project Specific Invariant"
type: concept
status: active
created: 2026-09-14
tags: [security, project-only]
summary: "Specific to this project."
---
# Project Specific Invariant
Detailed content here.
""", encoding="utf-8")

        # Add personal page
        (self.personal_vault_path / "skills" / "SKILL-GLOBAL.md").write_text("""---
id: SKILL-GLOBAL
title: "Universal Python Performance Profiling"
type: skill
status: active
created: 2026-09-14
tags: [profiling, python, universal]
summary: "Global personal skill across all projects."
---
# Universal Profiling
Run cProfile and snakeviz.
""", encoding="utf-8")

        # Search across both vaults
        results = layered_recall(
            query="python",
            project_vault=self.vault_path,
            personal_vault=self.personal_vault_path,
            scope="all",
        )
        self.assertGreaterEqual(len(results), 1)
        global_res = next(r for r in results if r["id"] == "SKILL-GLOBAL")
        self.assertEqual(global_res["scope"], "personal")
        self.assertEqual(global_res["type"], "skill")

        # Search project only
        proj_results = layered_recall(
            query="invariant",
            project_vault=self.vault_path,
            personal_vault=self.personal_vault_path,
            scope="project",
        )
        self.assertEqual(len(proj_results), 1)
        self.assertEqual(proj_results[0]["scope"], "project")
        self.assertEqual(proj_results[0]["id"], "CON-0001")

    def test_multi_token_recall(self):
        """Test layered recall with multi-term query matching terms across title and summary."""
        init_vault(self.vault_path)
        skill_file = self.vault_path / "skills" / "SKILL-0001.md"
        meta = {
            "id": "SKILL-0001",
            "title": "跨平台文本哈希规范化通用准则",
            "type": "skill",
            "status": "active",
            "created": "2026-09-14",
            "tags": ["hash", "cross-platform"],
            "summary": "在进行任何 SHA-256 前，先将所有换行符替换为 \\n",
        }
        skill_file.write_text(dump_frontmatter(meta, "# Content"), encoding="utf-8")
        results = layered_recall("换行符 哈希", project_vault=self.vault_path, scope="project")
        self.assertGreaterEqual(len(results), 1)
        self.assertEqual(results[0]["id"], "SKILL-0001")

    def test_markdown_and_wikilinks_dual_read(self):
        """Test both standard Markdown links [text](path.md) and wikilinks [[path]] register in backlinks graph."""
        init_vault(self.vault_path)
        (self.vault_path / "concepts" / "CON-0001.md").write_text("""---
id: CON-0001
title: "Target Concept"
type: concept
status: active
created: 2026-09-14
---
# Target
""", encoding="utf-8")

        (self.vault_path / "concepts" / "CON-0002.md").write_text("""---
id: CON-0002
title: "Source Concept"
type: concept
status: active
created: 2026-09-14
---
# Source
Links via standard markdown link: [Target Concept](concepts/CON-0001.md)
And via relative dot-slash: [Target Concept](./concepts/CON-0001.md#anchor)
""", encoding="utf-8")

        rebuild_metadata(self.vault_path)
        backlinks_data = json.loads((self.vault_path / "meta" / "backlinks.json").read_text(encoding="utf-8"))
        self.assertIn("concepts/CON-0001.md", backlinks_data)
        self.assertIn("concepts/CON-0002.md", backlinks_data["concepts/CON-0001.md"])

        lint_res = lint_vault(self.vault_path)
        self.assertTrue(lint_res["passed"])
        self.assertEqual(len(lint_res["broken_links"]), 0)

    def test_code_block_links_ignored(self):
        """Test links inside fenced code blocks and inline code are ignored by link extraction."""
        text = """
```markdown
[[concepts/FAKE_FENCE]]
[Fake](concepts/FAKE_MD.md)
```
And inline: `[[concepts/FAKE_INLINE]]` and `[Inline](concepts/FAKE_INLINE.md)`
And real wikilink: [[concepts/REAL_LINK|Real Link]]
"""
        links = clean_and_extract_links(text)
        self.assertEqual(links, ["concepts/REAL_LINK"])

    def test_escaped_pipe_and_special_char_wikilinks(self):
        """Test wikilinks with escaped pipe \\| and special characters resolve cleanly."""
        text = "Check [[concepts/实体 (测试)\\|别名]] and [[CON-0001#section\\|Title]]."
        links = clean_and_extract_links(text)
        self.assertEqual(links, ["concepts/实体 (测试)", "CON-0001"])

    def test_sequence_number_gap_collision_avoidance(self):
        """Test sequence numbering avoids collisions even when intermediate files are deleted."""
        init_vault(self.vault_path)
        today = datetime.date.today().isoformat().replace("-", "")
        sources_dir = self.vault_path / "sources"

        # Create SRC-...-0001 and SRC-...-0003 (with gap at 0002)
        (sources_dir / f"SRC-{today}-0001.md").write_text("---\nid: SRC-0001\n---", encoding="utf-8")
        (sources_dir / f"SRC-{today}-0003.md").write_text("---\nid: SRC-0003\n---", encoding="utf-8")

        dest = capture_source(self.vault_path, title="New Source", source_location="mem", content="data")
        # Must allocate 0004, NOT 0003 (which would overwrite existing!)
        self.assertTrue(dest.name.endswith(f"SRC-{today}-0004.md"))

    def test_fallback_yaml_parser_inline_lists(self):
        """Test zero-dependency fallback YAML parser handles inline lists, booleans, and nulls."""
        import sys
        old_yaml = sys.modules.get("yaml")
        sys.modules["yaml"] = None  # Force zero-dependency parser branch
        try:
            sample = """---
id: CON-999
title: "Test Parser"
tags: [core, governance, "quoted tag"]
empty_list: []
active: true
disabled: false
null_val: null
---
Body text here"""
            meta, body = parse_frontmatter(sample)
            self.assertEqual(meta["id"], "CON-999")
            self.assertEqual(meta["tags"], ["core", "governance", "quoted tag"])
            self.assertEqual(meta["empty_list"], [])
            self.assertTrue(meta["active"])
            self.assertFalse(meta["disabled"])
            self.assertIsNone(meta["null_val"])
            self.assertIn("Body text here", body)
        finally:
            if old_yaml is not None:
                sys.modules["yaml"] = old_yaml

    def test_ensure_page_creation_and_idempotency(self):
        """Test ensure_page safely creates pages and returns existing ones without overwriting."""
        init_vault(self.vault_path)
        path1, created1 = ensure_page(
            vault=self.vault_path,
            page_type="concept",
            title="SSOT Principle",
            tags=["core", "architecture"],
            summary="Single source of truth rule.",
        )
        self.assertTrue(created1)
        self.assertTrue(path1.exists())

        # Calling again with same title returns existing page
        path2, created2 = ensure_page(
            vault=self.vault_path,
            page_type="concept",
            title="SSOT Principle",
        )
        self.assertFalse(created2)
        self.assertEqual(path1, path2)

    def test_ingest_source_batch_processing(self):
        """Test ingest_sources batches uningested sources and generates synthesis pages."""
        init_vault(self.vault_path)
        src_dest = capture_source(
            vault=self.vault_path,
            title="Raw Research Whitepaper",
            source_location="https://arxiv.org/abs/test",
            content="Key findings on agentic verification workflows.",
            summary="Essential distillation on agent architectures.",
        )
        self.assertTrue(src_dest.exists())

        ingested = ingest_sources(self.vault_path)
        self.assertEqual(len(ingested), 1)
        self.assertTrue(ingested[0]["created"])

        # Check synthesis page was generated
        syn_page = self.vault_path / "synthesis" / ingested[0]["synthesis_page"]
        self.assertTrue(syn_page.exists())
        content = syn_page.read_text(encoding="utf-8")
        self.assertIn("Raw Research Whitepaper", content)

        # Source is marked ingested
        meta, _ = parse_frontmatter(src_dest.read_text(encoding="utf-8"))
        self.assertTrue(meta.get("ingested"))

    def test_search_registry(self):
        """Test search_registry queries over IDs, titles, and summaries."""
        init_vault(self.vault_path)
        ensure_page(
            vault=self.vault_path,
            page_type="entity",
            title="Validation Auditor",
            page_id="ENT-0001",
            aliases=["Auditor", "VAL"],
            summary="Independent verification agent.",
        )
        results = search_registry(self.vault_path, "Auditor")
        self.assertGreaterEqual(len(results), 1)
        self.assertEqual(results[0]["id"], "ENT-0001")

    def test_watch_schedule_output(self):
        """Test print_watch_schedule generates valid crontab commands."""
        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            print_watch_schedule(self.vault_path, schedule="daily")
        out = f.getvalue()
        self.assertIn("0 0 * * *", out)
        self.assertIn("rebuild-meta", out)
        self.assertIn("lint --fix", out)

    def test_vault_event_logging_audit_trail(self):
        """Test log_vault_event writes structured events to events.jsonl and meta/log.md."""
        init_vault(self.vault_path)
        log_vault_event(self.vault_path, "WIKI_TEST", "OBJ-001", "Test audit entry")
        events_file = self.vault_path / "meta" / "events.jsonl"
        log_file = self.vault_path / "meta" / "log.md"

        self.assertTrue(events_file.exists())
        lines = [line.strip() for line in events_file.read_text(encoding="utf-8").splitlines() if line.strip()]
        self.assertGreaterEqual(len(lines), 1)
        rec = json.loads(lines[-1])
        self.assertEqual(rec["event_type"], "WIKI_TEST")
        self.assertEqual(rec["target_object"], "OBJ-001")

        log_content = log_file.read_text(encoding="utf-8")
        self.assertIn("WIKI_TEST", log_content)
        self.assertIn("OBJ-001", log_content)

    def test_wiki_root_env_resolution(self):
        """Test resolve_project_vault respects WIKI_ROOT environment variable."""
        init_vault(self.vault_path)
        old_env = os.environ.get("WIKI_ROOT")
        os.environ["WIKI_ROOT"] = str(self.vault_path)
        try:
            resolved = resolve_project_vault()
            self.assertEqual(resolved, self.vault_path.resolve())
        finally:
            if old_env is not None:
                os.environ["WIKI_ROOT"] = old_env
            else:
                os.environ.pop("WIKI_ROOT", None)


if __name__ == "__main__":
    unittest.main()
