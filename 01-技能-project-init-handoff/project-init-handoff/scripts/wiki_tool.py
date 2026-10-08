#!/usr/bin/env python3
"""
wiki_tool.py - LLM Wiki & Knowledge Compounding Engine
Adheres to:
  - Andrej Karpathy's LLM Wiki Paradigm (persistent, compounding, cross-referencing markdown artifacts)
  - Open Knowledge Format (OKF v0.2) specification (standard YAML frontmatter, wikilinks & markdown links, stable IDs)
  - Layered Vault Architecture (Personal ~/.llm-wiki/ + Project {project}/05_研究资产/wiki/ or .llm-wiki/)
  - Agent Working Memory & Trajectory Distillation (record-trajectory -> distill-skill -> recall)
  - Deterministic Metadata Projections & Mechanical Linting (index.md, registry, backlinks, orphans, broken links)
  - pi-llm-wiki parity: ensure-page, ingest, search, watch, recall-skill
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

try:
    import fcntl
except ImportError:
    fcntl = None


def compute_content_sha256(content: str | bytes) -> str:
    """Compute SHA-256 hash of string or bytes."""
    if isinstance(content, str):
        content = content.encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def compute_file_sha256(filepath: Path) -> str:
    """Compute SHA-256 hash of a file on disk."""
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def parse_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    """
    Parse YAML frontmatter from markdown content with zero external dependencies.
    Gracefully uses PyYAML if installed; falls back to robust regex parser.
    """
    if not content.startswith("---"):
        return {}, content
    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}, content

    yaml_text = parts[1]
    body = parts[2]
    meta: dict[str, Any] = {}

    try:
        import yaml  # type: ignore
        loaded = yaml.safe_load(yaml_text)
        if isinstance(loaded, dict):
            return loaded, body
    except Exception:
        pass

    # Built-in robust zero-dependency YAML subset parser
    current_key: str | None = None
    in_list = False
    list_items: list[str] = []

    for line in yaml_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        if stripped.startswith("- ") and current_key:
            in_list = True
            item_val = stripped[2:].strip().strip('"').strip("'")
            list_items.append(item_val)
            meta[current_key] = list_items
            continue

        if ":" in line:
            if in_list and current_key:
                in_list = False
                list_items = []

            k, v = line.split(":", 1)
            k = k.strip()
            v = v.strip()
            current_key = k

            if not v:
                # Key with empty value or starting an indented list
                in_list = True
                list_items = []
                meta[k] = []
            elif v.startswith("[") and v.endswith("]"):
                # Inline array: [a, b, c] or []
                inner = v[1:-1].strip()
                if not inner:
                    meta[k] = []
                else:
                    items = [it.strip().strip('"').strip("'") for it in inner.split(",") if it.strip()]
                    meta[k] = items
            else:
                v_clean = v.strip('"').strip("'")
                if v_clean.lower() in ("true", "false"):
                    meta[k] = (v_clean.lower() == "true")
                elif v_clean.lower() in ("null", "~", "none"):
                    meta[k] = None
                else:
                    meta[k] = v_clean

    return meta, body


def dump_frontmatter(meta: dict[str, Any], body: str) -> str:
    """Format frontmatter and body into canonical markdown document."""
    lines = ["---"]
    for k, v in meta.items():
        if isinstance(v, list):
            lines.append(f"{k}:")
            for item in v:
                lines.append(f"  - \"{item}\"")
        elif isinstance(v, bool):
            lines.append(f"{k}: {'true' if v else 'false'}")
        elif v is None:
            lines.append(f"{k}: null")
        else:
            v_str = str(v).replace('"', '\\"')
            if "\n" in v_str:
                lines.append(f"{k}: >-\n  {v_str.replace(chr(10), chr(10) + '  ')}")
            else:
                lines.append(f"{k}: \"{v_str}\"")
    lines.append("---")
    header = "\n".join(lines)
    if not body.startswith("\n"):
        header += "\n"
    return header + body


def resolve_personal_vault() -> Path:
    """Return default personal vault path ~/.llm-wiki."""
    return Path.home() / ".llm-wiki"


def resolve_project_vault(start_dir: Path | None = None) -> Path | None:
    """
    Search for project wiki vault starting from start_dir up to root.
    Prioritizes WIKI_ROOT environment variable if set.
    Candidate patterns:
      1. <dir>/05_研究资产/wiki
      2. <dir>/05_资产库/wiki
      3. <dir>/.llm-wiki
      4. <dir>/wiki
    """
    env_root = os.environ.get("WIKI_ROOT")
    if env_root:
        p = Path(env_root).resolve()
        if p.exists() and p.is_dir():
            return p

    curr = (start_dir or Path.cwd()).resolve()
    for directory in [curr, *curr.parents]:
        for candidate in [
            directory / "05_研究资产" / "wiki",
            directory / "05_资产库" / "wiki",
            directory / ".llm-wiki",
            directory / "wiki",
        ]:
            if candidate.exists() and candidate.is_dir():
                return candidate
    return None


WIKI_SUBDIRS = [
    "concepts",
    "entities",
    "synthesis",
    "retro",
    "trajectories",
    "skills",
    "sources",
    "meta",
]


def init_vault(target_path: Path, is_personal: bool = False) -> None:
    """Initialize a compliant OKF v0.2 wiki vault."""
    target_path.mkdir(parents=True, exist_ok=True)
    for sub in WIKI_SUBDIRS:
        (target_path / sub).mkdir(parents=True, exist_ok=True)

    today = datetime.date.today().isoformat()
    vault_name = "Personal LLM Wiki" if is_personal else f"Project Wiki ({target_path.parent.name})"

    # 1. config.json (OKF v0.2 explicit mode specification)
    config_file = target_path / "config.json"
    if not config_file.exists():
        cfg_data = {
            "knowledge_format": "okf-0.2",
            "vault_name": vault_name,
            "created": today,
            "version": "0.2",
        }
        config_file.write_text(json.dumps(cfg_data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # 2. README.md
    readme_file = target_path / "README.md"
    if not readme_file.exists():
        readme_content = f"""---
id: WIKI-ROOT
title: "{vault_name}"
type: index
status: active
okf_version: "0.2"
created: {today}
updated: {today}
---

# {vault_name}

基于 Andrej Karpathy LLM Wiki 模式构建的自维护、可复利知识库，完全兼容 Open Knowledge Format (OKF v0.2) 与 Obsidian 双向链接。

## 目录结构说明

- `concepts/`: 核心领域概念与原子定义 (`CON-XXXX`)
- `entities/`: 系统组件、实体对象与接口边界 (`ENT-XXXX`)
- `synthesis/`: 跨文档/实践深度综合、方案对比与全景技术评估 (`SYN-XXXX`)
- `retro/`: 任务执行复盘、踩坑教训与原子工程洞察 (`RETRO-XXXX`)
- `trajectories/`: Agent 求解过程、工具调用序列与工作记忆 (`TRAJ-XXXX`)
- `skills/`: 从轨迹中提炼的可复用标准操作与排障范式 (`SKILL-XXXX`)
- `sources/`: 经哈希校验的不可变原始来源捕获包 (`SRC-XXXX`)
- `meta/`: 确定性自动投影目录（`index.md` 索引、`observations.md` 实时记录、`events.jsonl`、`log.md`、图谱与注册表）

## 治理与维护原则

1. **增量复利 (Compounding)**: 知识在此沉淀而非随会话流逝，越积累越完备；
2. **单事实源与双向链接**: 广泛使用 `[[wikilinks]]` 与 `[Markdown](links)` 连接概念与实操凭据；
3. **确定性投影**: `meta/index.md` 可随时通过 `wiki_tool.py rebuild-meta` 完整重构。
"""
        readme_file.write_text(readme_content, encoding="utf-8")

    # 3. meta/index.md
    index_file = target_path / "meta" / "index.md"
    if not index_file.exists():
        index_content = f"""---
id: META-INDEX
title: "Wiki 结构化总索引 (Catalog)"
type: index
status: active
okf_version: "0.2"
created: {today}
updated: {today}
---

# Wiki 知识库结构化总索引

本索引为内容导向的确定性元数据投影，由 `wiki_tool.py rebuild-meta` 自动构建并保持同步。

## 1. 核心概念 (Concepts)
*暂无已归档概念*

## 2. 实体与组件 (Entities)
*暂无已归档实体*

## 3. 综合分析 (Synthesis)
*暂无已归档综合分析*

## 4. 任务复盘与原子洞察 (Retrospectives)
*暂无已归档复盘*

## 5. 提炼技能与最佳实践 (Skills & Playbooks)
*暂无已提炼技能*

## 6. Agent 求解轨迹 (Trajectories)
*暂无已记录轨迹*

## 7. 原始来源包 (Sources)
*暂无已捕获来源*
"""
        index_file.write_text(index_content, encoding="utf-8")

    # 4. meta/observations.md
    obs_file = target_path / "meta" / "observations.md"
    if not obs_file.exists():
        obs_content = f"""---
id: META-OBSERVATIONS
title: "会话实时观察与备忘日志 (Session Observations)"
type: meta
status: active
okf_version: "0.2"
created: {today}
updated: {today}
---

# 会话实时观察与备忘日志

记录 Agent 在工作会话中发现的临时约束、环境特异性与关键观察，后续可提炼至概念或技能。

"""
        obs_file.write_text(obs_content, encoding="utf-8")

    # 5. meta/events.jsonl & meta/log.md (OKF audit log)
    events_file = target_path / "meta" / "events.jsonl"
    if not events_file.exists():
        events_file.write_text("", encoding="utf-8")

    log_file = target_path / "meta" / "log.md"
    if not log_file.exists():
        log_content = f"""---
id: META-LOG
title: "Wiki 事务审计日志 (Transaction Log)"
type: meta
status: active
okf_version: "0.2"
created: {today}
updated: {today}
---

# Wiki 事务审计日志

| 时间 (Timestamp) | 事件 (Event) | 对象 (Object) | 说明 (Summary) |
|---|---|---|---|
| {today} | WIKI_INIT | WIKI-ROOT | 初始化 OKF v0.2 Wiki Vault |
"""
        log_file.write_text(log_content, encoding="utf-8")

    # 6. meta/backlinks.json & meta/registry.json
    backlinks_file = target_path / "meta" / "backlinks.json"
    if not backlinks_file.exists():
        backlinks_file.write_text("{}", encoding="utf-8")

    registry_file = target_path / "meta" / "registry.json"
    if not registry_file.exists():
        registry_file.write_text("{}", encoding="utf-8")


def log_vault_event(
    vault: Path,
    event_type: str,
    target_object: str,
    summary: str,
    evidence_path: Path | None = None,
) -> None:
    """
    Log structured event to vault's meta/events.jsonl and meta/log.md,
    and best-effort log to project 07_运行记录/LOG.md.
    """
    now_dt = datetime.datetime.now()
    ts_iso = now_dt.isoformat(timespec="seconds")

    # 1. meta/events.jsonl
    events_file = vault / "meta" / "events.jsonl"
    event_record = {
        "timestamp": ts_iso,
        "event_type": event_type,
        "target_object": target_object,
        "summary": summary,
        "evidence": evidence_path.as_posix() if evidence_path else "",
    }
    try:
        events_file.parent.mkdir(parents=True, exist_ok=True)
        with open(events_file, "a", encoding="utf-8") as f:
            if fcntl:
                try:
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                except OSError:
                    pass
            f.write(json.dumps(event_record, ensure_ascii=False) + "\n")
            if fcntl:
                try:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                except OSError:
                    pass
    except Exception:
        pass

    # 2. meta/log.md
    log_file = vault / "meta" / "log.md"
    if log_file.exists():
        row = f"| {ts_iso} | {event_type} | `{target_object}` | {summary.replace('|', '\\|')} |\n"
        try:
            with open(log_file, "a", encoding="utf-8") as f:
                if fcntl:
                    try:
                        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                    except OSError:
                        pass
                f.write(row)
                if fcntl:
                    try:
                        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                    except OSError:
                        pass
        except Exception:
            pass

    # 3. Project 07_运行记录/LOG.md
    try_log_project_event(vault, event_type=event_type, target_object=target_object, change_desc=summary, evidence_path=evidence_path)


def try_log_project_event(
    vault: Path,
    event_type: str,
    target_object: str,
    change_desc: str,
    evidence_path: Path | None = None,
) -> None:
    """Best-effort logging to 07_运行记录/LOG.md if present in the project tree."""
    curr = vault.resolve()
    for p in [curr, *curr.parents]:
        log_file = p / "07_运行记录" / "LOG.md"
        if log_file.exists():
            try:
                scripts_dir = Path(__file__).resolve().parent
                if str(scripts_dir) not in sys.path:
                    sys.path.insert(0, str(scripts_dir))
                from log_event import append_event

                if evidence_path:
                    try:
                        ev_str = str(evidence_path.resolve().relative_to(p))
                    except ValueError:
                        ev_str = str(evidence_path)
                else:
                    ev_str = str(vault.relative_to(p))

                append_event(
                    log_path=log_file,
                    event_type=event_type,
                    target_object=target_object,
                    change_desc=change_desc,
                    evidence=ev_str,
                    next_step="继续知识累积或切片执行",
                )
            except Exception:
                pass
            break


def clean_and_extract_links(text: str) -> list[str]:
    """
    Extract internal target paths from Wikilinks [[link]] and Markdown links [text](link).
    - Ignores fenced code blocks and inline code snippets.
    - Handles escaped pipes \\| and aliases in wikilinks.
    - Handles section anchors #.
    - Ignores external URLs and in-page anchor-only links.
    """
    # 1. Strip fenced code blocks
    text_no_code = re.sub(r"```[\s\S]*?```", "", text)
    # 2. Strip inline code
    text_no_code = re.sub(r"`[^`\n]+`", "", text_no_code)

    links: list[str] = []

    # Wikilinks: [[target|alias]] or [[target\|alias]] or [[target#anchor|alias]] or [[target]]
    wikilink_pat = re.compile(r"\[\[([^\]\n]+)\]\]")
    for match in wikilink_pat.finditer(text_no_code):
        raw = match.group(1).strip()
        # Handle escaped pipe \| as standard pipe |
        raw = raw.replace(r"\|", "|")
        # Split on alias pipe
        parts = raw.split("|", 1)
        target = parts[0].strip()
        # Strip anchor #
        target = target.split("#", 1)[0].strip()
        if target:
            links.append(target)

    # Markdown links: [text](target)
    mdlink_pat = re.compile(r"(?<!!)\[[^\]]*\]\(([^)\n]+)\)")
    for match in mdlink_pat.finditer(text_no_code):
        raw = match.group(1).strip()
        if not raw or raw.startswith(("http://", "https://", "ftp://", "mailto:", "#")):
            continue
        # Split on title in quotes if any: (path "title")
        raw = raw.split()[0].strip()
        # Strip anchor #
        target = raw.split("#", 1)[0].strip()
        if target:
            links.append(target)

    return links


# Backwards compatibility alias
extract_wikilinks = clean_and_extract_links


def scan_vault_pages(vault: Path) -> dict[str, dict[str, Any]]:
    """
    Scan all markdown files in vault (excluding meta/ projections and README.md).
    Returns dict: relative_path_str -> {path, meta, body, wikilinks, id, title, type}
    Uses posix path strings consistently across macOS, Linux, and Windows.
    """
    pages: dict[str, dict[str, Any]] = {}
    for p in vault.rglob("*.md"):
        rel_str = p.relative_to(vault).as_posix()
        # Skip meta projections and root README
        if rel_str.startswith("meta/") or rel_str == "README.md":
            continue

        try:
            content = p.read_text(encoding="utf-8")
            meta, body = parse_frontmatter(content)
            links = clean_and_extract_links(content)
            page_id = meta.get("id") or p.stem
            pages[rel_str] = {
                "path": p,
                "rel_path": rel_str,
                "meta": meta,
                "body": body,
                "wikilinks": links,
                "id": str(page_id),
                "title": str(meta.get("title") or p.stem),
                "type": str(meta.get("type") or "other"),
                "status": str(meta.get("status") or "active"),
                "summary": str(meta.get("summary") or ""),
                "tags": meta.get("tags") if isinstance(meta.get("tags"), list) else [],
                "aliases": meta.get("aliases") if isinstance(meta.get("aliases"), list) else [],
                "updated": str(meta.get("updated") or meta.get("created") or ""),
            }
        except Exception:
            continue
    return pages


def build_target_mapping(vault: Path, pages: dict[str, dict[str, Any]]) -> dict[str, str]:
    """Build normalization map from links/slugs/aliases to canonical posix rel_str."""
    target_to_rel: dict[str, str] = {}
    vault_name = vault.name

    for rel_str, pinfo in pages.items():
        stem = Path(rel_str).stem
        target_to_rel[rel_str] = rel_str
        target_to_rel[rel_str.replace(".md", "")] = rel_str
        target_to_rel[stem] = rel_str
        target_to_rel[pinfo["id"]] = rel_str

        # Project-relative prefixes support
        target_to_rel[f"{vault_name}/{rel_str}"] = rel_str
        target_to_rel[f"{vault_name}/{rel_str.replace('.md', '')}"] = rel_str
        target_to_rel[f"05_研究资产/wiki/{rel_str}"] = rel_str
        target_to_rel[f"05_研究资产/wiki/{rel_str.replace('.md', '')}"] = rel_str
        target_to_rel[f"05_资产库/wiki/{rel_str}"] = rel_str
        target_to_rel[f"05_资产库/wiki/{rel_str.replace('.md', '')}"] = rel_str
        target_to_rel[f".llm-wiki/{rel_str}"] = rel_str
        target_to_rel[f".llm-wiki/{rel_str.replace('.md', '')}"] = rel_str

        for alias in pinfo["aliases"]:
            target_to_rel[alias] = rel_str

    return target_to_rel


def rebuild_metadata(vault: Path) -> dict[str, Any]:
    """
    Deterministic metadata rebuild:
      1. Scans all pages in vault
      2. Rebuilds meta/index.md
      3. Rebuilds meta/backlinks.json
      4. Rebuilds meta/registry.json
    """
    pages = scan_vault_pages(vault)
    today = datetime.date.today().isoformat()
    target_to_rel = build_target_mapping(vault, pages)

    backlinks: dict[str, list[str]] = {rel_str: [] for rel_str in pages}
    for source_rel, pinfo in pages.items():
        for link in pinfo["wikilinks"]:
            clean_link = link.strip().replace("\\", "/")
            if clean_link.startswith("./"):
                clean_link = clean_link[2:]
            target_rel = target_to_rel.get(clean_link) or target_to_rel.get(Path(clean_link).stem)
            if target_rel and target_rel in backlinks:
                if source_rel not in backlinks[target_rel]:
                    backlinks[target_rel].append(source_rel)

    # Write backlinks.json
    backlinks_file = vault / "meta" / "backlinks.json"
    backlinks_file.write_text(json.dumps(backlinks, indent=2, ensure_ascii=False), encoding="utf-8")

    # Build registry
    registry: dict[str, Any] = {}
    for rel_str, pinfo in pages.items():
        registry[pinfo["id"]] = {
            "rel_path": rel_str,
            "title": pinfo["title"],
            "type": pinfo["type"],
            "status": pinfo["status"],
            "tags": pinfo["tags"],
            "aliases": pinfo["aliases"],
            "summary": pinfo["summary"],
            "updated": pinfo["updated"],
            "inbound_links_count": len(backlinks.get(rel_str, [])),
        }
    registry_file = vault / "meta" / "registry.json"
    registry_file.write_text(json.dumps(registry, indent=2, ensure_ascii=False), encoding="utf-8")

    # Reconstruct meta/index.md by category
    categories = [
        ("concept", "1. 核心概念 (Concepts)"),
        ("entity", "2. 实体与组件 (Entities)"),
        ("synthesis", "3. 综合分析 (Synthesis)"),
        ("retro", "4. 任务复盘与原子洞察 (Retrospectives)"),
        ("skill", "5. 提炼技能与最佳实践 (Skills & Playbooks)"),
        ("trajectory", "6. Agent 求解轨迹 (Trajectories)"),
        ("source", "7. 原始来源包 (Sources)"),
        ("other", "8. 其他知识条目 (Other Pages)"),
    ]

    index_lines = [
        "---",
        "id: META-INDEX",
        'title: "Wiki 结构化总索引 (Catalog)"',
        "type: index",
        "status: active",
        'okf_version: "0.2"',
        f"created: {today}",
        f"updated: {today}",
        "---",
        "",
        "# Wiki 知识库结构化总索引",
        "",
        "本索引为内容导向的确定性元数据投影，由 `wiki_tool.py rebuild-meta` 自动构建并保持同步。",
        "",
    ]

    for cat_type, cat_heading in categories:
        cat_pages = [p for p in pages.values() if p["type"] == cat_type]
        index_lines.append(f"## {cat_heading}")
        if not cat_pages:
            index_lines.append("*暂无条目*\n")
        else:
            index_lines.append("| ID | 标题 / 链接 | 状态 | 标签 | 摘要 |")
            index_lines.append("|---|---|---|---|---|")
            for p in sorted(cat_pages, key=lambda x: x["id"]):
                link = f"[[{p['rel_path']}|{p['title']}]]"
                tags_str = ", ".join(p["tags"]) if p["tags"] else "-"
                summary_str = p["summary"].replace("|", "\\|") if p["summary"] else "-"
                index_lines.append(f"| `{p['id']}` | {link} | `{p['status']}` | {tags_str} | {summary_str} |")
            index_lines.append("")

    index_file = vault / "meta" / "index.md"
    index_file.write_text("\n".join(index_lines), encoding="utf-8")

    return {
        "total_pages": len(pages),
        "backlinks_count": sum(len(v) for v in backlinks.values()),
        "categories_count": {c: len([p for p in pages.values() if p["type"] == c]) for c, _ in categories},
    }


def lint_vault(vault: Path, auto_fix: bool = False) -> dict[str, Any]:
    """
    Perform deterministic mechanical linting on the vault:
      - Broken wikilinks / markdown links
      - Orphan pages (zero inbound links, not linked anywhere)
      - Missing / malformed OKF frontmatter
      - Duplicate IDs or duplicate aliases
      - Unindexed pages in meta/index.md
    """
    pages = scan_vault_pages(vault)
    broken_links: list[dict[str, str]] = []
    frontmatter_errors: list[dict[str, str]] = []
    duplicate_ids: dict[str, list[str]] = {}
    duplicate_aliases: dict[str, list[str]] = {}

    target_to_rel = build_target_mapping(vault, pages)
    id_map: dict[str, list[str]] = {}
    alias_map: dict[str, list[str]] = {}

    for rel_str, pinfo in pages.items():
        pid = pinfo["id"]
        id_map.setdefault(pid, []).append(rel_str)
        for a in pinfo["aliases"]:
            alias_map.setdefault(a, []).append(rel_str)

        # Check required OKF v0.2 frontmatter fields
        meta = pinfo["meta"]
        missing_fields = [f for f in ["id", "title", "type", "status", "created"] if not meta.get(f)]
        if missing_fields:
            frontmatter_errors.append({
                "file": rel_str,
                "error": f"Missing required frontmatter fields: {', '.join(missing_fields)}",
            })

    for pid, paths in id_map.items():
        if len(paths) > 1:
            duplicate_ids[pid] = paths

    for alias, paths in alias_map.items():
        if len(paths) > 1:
            duplicate_aliases[alias] = paths

    inbound_counts: dict[str, int] = {rel_str: 0 for rel_str in pages}
    for source_rel, pinfo in pages.items():
        for link in pinfo["wikilinks"]:
            clean_link = link.strip().replace("\\", "/")
            if clean_link.startswith("./"):
                clean_link = clean_link[2:]

            resolved = target_to_rel.get(clean_link) or target_to_rel.get(Path(clean_link).stem)
            if not resolved:
                # Reserved meta paths
                if clean_link in ("meta/index", "meta/observations", "meta/log", "README", "00_入口/00_当前"):
                    continue
                broken_links.append({
                    "source": source_rel,
                    "target": link,
                })
            else:
                inbound_counts[resolved] = inbound_counts.get(resolved, 0) + 1

    # Identify orphans: inbound count == 0 and not source packet (sources are leaf evidence)
    orphans: list[str] = []
    for rel_str, count in inbound_counts.items():
        if count == 0 and pages[rel_str]["type"] not in ("source", "index"):
            orphans.append(rel_str)

    # Check unindexed pages in meta/index.md
    index_file = vault / "meta" / "index.md"
    index_text = index_file.read_text(encoding="utf-8") if index_file.exists() else ""
    unindexed_pages: list[str] = []
    for rel_str in pages:
        if rel_str not in index_text and pages[rel_str]["id"] not in index_text:
            unindexed_pages.append(rel_str)

    if auto_fix and unindexed_pages:
        rebuild_metadata(vault)
        unindexed_pages = []

    passed = (
        len(broken_links) == 0
        and len(frontmatter_errors) == 0
        and len(duplicate_ids) == 0
        and len(duplicate_aliases) == 0
        and len(unindexed_pages) == 0
    )

    return {
        "passed": passed,
        "total_pages_scanned": len(pages),
        "broken_links": broken_links,
        "frontmatter_errors": frontmatter_errors,
        "duplicate_ids": duplicate_ids,
        "duplicate_aliases": duplicate_aliases,
        "orphans": orphans,
        "unindexed_pages": unindexed_pages,
    }


def capture_source(
    vault: Path,
    title: str,
    source_location: str,
    content: str,
    source_type: str = "text",
    tags: list[str] | None = None,
    summary: str = "",
) -> Path:
    """Capture an immutable source packet with SHA-256 into sources/."""
    today = datetime.date.today().isoformat()
    date_compact = today.replace("-", "")

    sources_dir = vault / "sources"
    sources_dir.mkdir(parents=True, exist_ok=True)

    # Sequence numbering with gap protection
    existing_files = list(sources_dir.glob(f"SRC-{date_compact}-*.md"))
    existing_nums = []
    for p in existing_files:
        m = re.search(rf"SRC-{date_compact}-(\d{{4}})", p.name)
        if m:
            existing_nums.append(int(m.group(1)))
    next_num = max(existing_nums) + 1 if existing_nums else 1
    while (sources_dir / f"SRC-{date_compact}-{next_num:04d}.md").exists():
        next_num += 1

    source_id = f"SRC-{date_compact}-{next_num:04d}"
    content_hash = compute_content_sha256(content)
    meta = {
        "id": source_id,
        "title": title,
        "type": "source",
        "status": "immutable",
        "created": today,
        "updated": today,
        "source_type": source_type,
        "source_location": source_location,
        "source_sha256": content_hash,
        "tags": tags or ["source"],
        "summary": summary or f"Captured from {source_location}",
    }

    body = f"""
# {title}

## 1. 来源元数据 (Metadata)
- **原始位置**: `{source_location}`
- **内容 SHA-256**: `{content_hash}`
- **捕获日期**: {today}

## 2. 核心摘要 (Summary)
{summary or '无详细摘要。'}

## 3. 原始记录 (Raw Content)
```text
{content.strip()}
```
"""
    dest = sources_dir / f"{source_id}.md"
    dest.write_text(dump_frontmatter(meta, body), encoding="utf-8")
    rebuild_metadata(vault)
    log_vault_event(vault, "WIKI_INGEST", source_id, f"捕获来源包: {title}", evidence_path=dest)
    return dest


def record_retro(
    vault: Path,
    title: str,
    insight: str,
    task_slice: str = "",
    context: str = "",
    tags: list[str] | None = None,
    summary: str = "",
) -> Path:
    """Record an atomic insight or post-task retrospective."""
    today = datetime.date.today().isoformat()
    date_compact = today.replace("-", "")

    retro_dir = vault / "retro"
    retro_dir.mkdir(parents=True, exist_ok=True)

    existing_files = list(retro_dir.glob(f"RETRO-{date_compact}-*.md"))
    existing_nums = []
    for p in existing_files:
        m = re.search(rf"RETRO-{date_compact}-(\d{{4}})", p.name)
        if m:
            existing_nums.append(int(m.group(1)))
    next_num = max(existing_nums) + 1 if existing_nums else 1
    while (retro_dir / f"RETRO-{date_compact}-{next_num:04d}.md").exists():
        next_num += 1

    retro_id = f"RETRO-{date_compact}-{next_num:04d}"

    meta: dict[str, Any] = {
        "id": retro_id,
        "title": title,
        "type": "retro",
        "status": "active",
        "created": today,
        "updated": today,
        "tags": tags or ["retro", "insight"],
        "summary": summary or insight[:120].strip(),
    }
    if task_slice:
        meta["task_slice_ref"] = task_slice

    body = f"""
# {title}

## 1. 产生背景 (Context)
- 关联切片：{task_slice or '全局/通用'}
- 上下文：{context or '常规会话任务执行。'}

## 2. 核心原子洞察 (Atomic Insight)
{insight}

## 3. 规避指南与落地建议 (Recommendations)
- 遵循原则：在后续相同场景下前置校验。
- 链接引用：[[meta/index|查看知识库总索引]]
"""
    dest = retro_dir / f"{retro_id}.md"
    dest.write_text(dump_frontmatter(meta, body), encoding="utf-8")
    rebuild_metadata(vault)
    log_vault_event(vault, "WIKI_RETRO", retro_id, f"沉淀原子洞察: {title}", evidence_path=dest)
    return dest


def record_trajectory(
    vault: Path,
    title: str,
    objective: str,
    steps: str,
    task_slice: str = "",
    bottlenecks: str = "",
    breakthrough: str = "",
    outcome: str = "",
    tags: list[str] | None = None,
    summary: str = "",
) -> Path:
    """Record agent working-memory problem-solving trajectory."""
    today = datetime.date.today().isoformat()
    date_compact = today.replace("-", "")

    traj_dir = vault / "trajectories"
    traj_dir.mkdir(parents=True, exist_ok=True)

    existing_files = list(traj_dir.glob(f"TRAJ-{date_compact}-*.md"))
    existing_nums = []
    for p in existing_files:
        m = re.search(rf"TRAJ-{date_compact}-(\d{{4}})", p.name)
        if m:
            existing_nums.append(int(m.group(1)))
    next_num = max(existing_nums) + 1 if existing_nums else 1
    while (traj_dir / f"TRAJ-{date_compact}-{next_num:04d}.md").exists():
        next_num += 1

    traj_id = f"TRAJ-{date_compact}-{next_num:04d}"

    meta: dict[str, Any] = {
        "id": traj_id,
        "title": title,
        "type": "trajectory",
        "status": "recorded",
        "created": today,
        "updated": today,
        "tags": tags or ["trajectory", "agent-memory"],
        "summary": summary or objective[:120].strip(),
    }
    if task_slice:
        meta["task_slice_ref"] = task_slice

    body = f"""
# {title}

## 1. 目标与初始边界 (Objective)
- 任务切片: {task_slice or '未指定'}
- 目标: {objective}

## 2. 工具调用序列与求解历程 (Execution Steps)
{steps}

## 3. 遭遇阻碍与踩坑 (Bottlenecks & Hurdles)
{bottlenecks or '无明显阻塞。'}

## 4. 突破点与关键解法 (Breakthrough)
{breakthrough or '按既定方案顺利达成。'}

## 5. 产出结论 (Outcome)
{outcome or '已产出候选并通过验证。'}
"""
    dest = traj_dir / f"{traj_id}.md"
    dest.write_text(dump_frontmatter(meta, body), encoding="utf-8")
    rebuild_metadata(vault)
    log_vault_event(vault, "WIKI_TRAJECTORY", traj_id, f"记录求解轨迹: {title}", evidence_path=dest)
    return dest


def distill_skill(
    vault: Path,
    title: str,
    pattern: str,
    trajectories: list[str],
    antipatterns: str = "",
    checklist: list[str] | None = None,
    tags: list[str] | None = None,
    summary: str = "",
) -> Path:
    """Distill one or more trajectories into a reusable skill/playbook page."""
    today = datetime.date.today().isoformat()
    skills_dir = vault / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)

    existing_files = list(skills_dir.glob("SKILL-*.md"))
    existing_nums = []
    for p in existing_files:
        m = re.search(r"SKILL-(\d{4})", p.name)
        if m:
            existing_nums.append(int(m.group(1)))
    next_num = max(existing_nums) + 1 if existing_nums else 1
    while (skills_dir / f"SKILL-{next_num:04d}.md").exists():
        next_num += 1

    skill_id = f"SKILL-{next_num:04d}"

    meta = {
        "id": skill_id,
        "title": title,
        "type": "skill",
        "status": "active",
        "created": today,
        "updated": today,
        "trajectories": trajectories,
        "tags": tags or ["skill", "playbook"],
        "summary": summary or pattern[:120].strip(),
    }

    checklist_md = "\n".join([f"- [ ] {c}" for c in (checklist or ["验证基本功能", "执行边界测试"])])
    body = f"""
# {title}

## 1. 触发场景与适用条件 (Applicability)
当遇到类似问题时，优先参考本标准化解题范式。

## 2. 标准解题范式 (Proven Pattern)
{pattern}

## 3. 典型陷阱与反模式 (Anti-Patterns)
{antipatterns or '暂无特别反模式。'}

## 4. 验收自检清单 (Verification Checklist)
{checklist_md}

## 5. 来源轨迹 (Source Trajectories)
{chr(10).join([f"- [[trajectories/{t}|{t}]]" for t in trajectories])}
"""
    dest = skills_dir / f"{skill_id}.md"
    dest.write_text(dump_frontmatter(meta, body), encoding="utf-8")

    # Mark referenced trajectories as distilled
    traj_dir = vault / "trajectories"
    for t in trajectories:
        t_file = traj_dir / f"{t}.md"
        if t_file.exists():
            t_meta, t_body = parse_frontmatter(t_file.read_text(encoding="utf-8"))
            t_meta["status"] = "distilled"
            t_meta["updated"] = today
            t_file.write_text(dump_frontmatter(t_meta, t_body), encoding="utf-8")

    rebuild_metadata(vault)
    log_vault_event(vault, "WIKI_DISTILL", skill_id, f"提炼通用技能: {title}", evidence_path=dest)
    return dest


def append_observation(vault: Path, text: str, author: str = "Agent", tags: list[str] | None = None) -> None:
    """Append a timestamped observation to meta/observations.md safely with file locking."""
    obs_file = vault / "meta" / "observations.md"
    if not obs_file.exists():
        init_vault(vault)

    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    tag_str = " ".join([f"#{t}" for t in (tags or [])])
    entry = f"### [{now_str}] {author} {tag_str}\n{text.strip()}\n\n"

    with open(obs_file, "a", encoding="utf-8") as f:
        if fcntl:
            try:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            except OSError:
                pass
        f.write(entry)
        if fcntl:
            try:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass

    log_vault_event(vault, "WIKI_OBSERVE", "OBSERVATION", f"{author}: {text[:60]}")


def ensure_page(
    vault: Path,
    page_type: str,
    title: str,
    page_id: str | None = None,
    content: str = "",
    tags: list[str] | None = None,
    aliases: list[str] | None = None,
    summary: str = "",
    sources: list[str] | None = None,
) -> tuple[Path, bool]:
    """
    Resolve or safely create an entity/concept/synthesis/retro/skill/source page.
    Returns (page_path, created_boolean).
    """
    type_subdirs = {
        "concept": "concepts",
        "entity": "entities",
        "synthesis": "synthesis",
        "retro": "retro",
        "trajectory": "trajectories",
        "skill": "skills",
        "source": "sources",
    }
    sub = type_subdirs.get(page_type.lower(), "concepts")
    target_dir = vault / sub
    target_dir.mkdir(parents=True, exist_ok=True)

    today = datetime.date.today().isoformat()
    date_compact = today.replace("-", "")

    pages = scan_vault_pages(vault)

    # 1. Check if page already exists by ID
    if page_id:
        for pinfo in pages.values():
            if pinfo["id"] == page_id:
                return Path(pinfo["path"]), False

    # 2. Check if page already exists by title or alias
    for pinfo in pages.values():
        if pinfo["title"].lower() == title.lower():
            return Path(pinfo["path"]), False
        if aliases:
            for a in aliases:
                if a in pinfo["aliases"]:
                    return Path(pinfo["path"]), False

    # 3. Generate page_id if not given
    if not page_id:
        type_prefixes = {
            "concept": "CON",
            "entity": "ENT",
            "synthesis": "SYN",
            "retro": f"RETRO-{date_compact}",
            "trajectory": f"TRAJ-{date_compact}",
            "skill": "SKILL",
            "source": f"SRC-{date_compact}",
        }
        prefix = type_prefixes.get(page_type.lower(), "PAGE")
        existing_files = list(target_dir.glob(f"{prefix}-*.md"))
        existing_nums = []
        for p in existing_files:
            m = re.search(rf"{prefix}-(\d{{4}})", p.name)
            if m:
                existing_nums.append(int(m.group(1)))
        next_num = max(existing_nums) + 1 if existing_nums else 1
        while (target_dir / f"{prefix}-{next_num:04d}.md").exists():
            next_num += 1
        page_id = f"{prefix}-{next_num:04d}"

    dest = target_dir / f"{page_id}.md"

    meta: dict[str, Any] = {
        "id": page_id,
        "title": title,
        "type": page_type,
        "status": "active",
        "created": today,
        "updated": today,
    }
    if aliases:
        meta["aliases"] = aliases
    if tags:
        meta["tags"] = tags
    if sources:
        meta["sources"] = sources
    if summary:
        meta["summary"] = summary

    body = content.strip() if content else f"# {title}\n\n{summary or '待补充详细内容。'}\n"
    if not body.startswith("#"):
        body = f"# {title}\n\n{body}\n"

    dest.write_text(dump_frontmatter(meta, body), encoding="utf-8")
    rebuild_metadata(vault)
    log_vault_event(vault, "WIKI_ENSURE_PAGE", page_id, f"创建 {page_type} 页面: {title}", evidence_path=dest)
    return dest, True


def ingest_sources(vault: Path, source_id: str | None = None) -> list[dict[str, Any]]:
    """
    Batch process uningested source packets into structured wiki synthesis pages.
    Returns list of processed items: [{source_id, title, synthesis_page, created}].
    """
    sources_dir = vault / "sources"
    if not sources_dir.exists():
        return []

    today = datetime.date.today().isoformat()
    candidates: list[Path] = []
    if source_id:
        src_path = sources_dir / f"{source_id}.md"
        if src_path.exists():
            candidates.append(src_path)
    else:
        candidates = sorted(list(sources_dir.glob("SRC-*.md")))

    results: list[dict[str, Any]] = []

    for src_path in candidates:
        content = src_path.read_text(encoding="utf-8")
        meta, body = parse_frontmatter(content)
        if meta.get("ingested"):
            continue

        sid = meta.get("id", src_path.stem)
        title = meta.get("title", sid)
        summary = meta.get("summary", "")
        tags = meta.get("tags", ["source", "ingested"])

        syn_title = f"来源综述: {title}"
        syn_body = f"""# {syn_title}

## 1. 来源追溯 (Provenance)
- 关联不可变来源包: [[sources/{sid}|{title}]]
- 来源类型: `{meta.get('source_type', 'unknown')}`
- 原始位置: `{meta.get('source_location', 'unknown')}`

## 2. 核心知识提炼 (Extracted Knowledge)
{summary or '从原始来源提炼的核心知识。'}

## 3. 规范化实体与关联 (Entities & Concepts)
- 参阅知识库总目录: [[meta/index|知识库总索引]]
"""
        syn_dest, created = ensure_page(
            vault=vault,
            page_type="synthesis",
            title=syn_title,
            content=syn_body,
            tags=tags if isinstance(tags, list) else [tags],
            sources=[sid],
            summary=summary or f"Ingested from {sid}",
        )

        meta["ingested"] = True
        meta["updated"] = today
        src_path.write_text(dump_frontmatter(meta, body), encoding="utf-8")

        results.append({
            "source_id": sid,
            "title": title,
            "synthesis_page": syn_dest.name,
            "created": created,
        })

    if results:
        rebuild_metadata(vault)
        for r in results:
            log_vault_event(
                vault,
                "WIKI_INGEST",
                r["source_id"],
                f"完成来源摄取并生成综合分析: {r['synthesis_page']}",
                evidence_path=vault / "synthesis" / r["synthesis_page"],
            )

    return results


def search_registry(vault: Path, query: str) -> list[dict[str, Any]]:
    """Fast registry search matching IDs, titles, aliases, tags, and summaries."""
    reg_file = vault / "meta" / "registry.json"
    if not reg_file.exists():
        rebuild_metadata(vault)

    try:
        reg = json.loads(reg_file.read_text(encoding="utf-8"))
    except Exception:
        reg = {}

    q_lower = query.lower().strip()
    tokens = [tok for tok in q_lower.split() if tok]
    results = []

    for pid, info in reg.items():
        title = info.get("title", "")
        summary = info.get("summary", "")
        tags = [t.lower() for t in info.get("tags", [])]
        aliases = [a.lower() for a in info.get("aliases", [])]

        score = 0
        if not q_lower:
            score = 1
        elif q_lower == pid.lower() or q_lower == title.lower():
            score += 100
        elif q_lower in title.lower() or q_lower in summary.lower():
            score += 50
        elif any(q_lower in a for a in aliases) or any(q_lower in t for t in tags):
            score += 40

        if tokens:
            for tok in tokens:
                if tok in pid.lower() or tok in title.lower() or tok in summary.lower():
                    score += 15
                if any(tok in a for a in aliases) or any(tok in t for t in tags):
                    score += 10

        if score > 0:
            results.append({
                "id": pid,
                "score": score,
                "rel_path": info.get("rel_path", ""),
                "title": title,
                "type": info.get("type", ""),
                "status": info.get("status", ""),
                "tags": info.get("tags", []),
                "summary": summary,
                "inbound_links_count": info.get("inbound_links_count", 0),
            })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results


def print_watch_schedule(vault: Path, schedule: str = "daily") -> None:
    """Print crontab line for automated wiki maintenance."""
    script_path = Path(__file__).resolve()
    vault_str = str(vault.resolve())

    cron_times = {
        "hourly": "0 * * * *",
        "daily": "0 0 * * *",
        "weekly": "0 0 * * 0",
    }
    cron_expr = cron_times.get(schedule.lower(), "0 0 * * *")

    print(f"# LLM-Wiki Automated Maintenance Schedule ({schedule})")
    print(f"# Vault: {vault_str}")
    print(f"{cron_expr} {sys.executable} {script_path} --vault '{vault_str}' lint --fix && {sys.executable} {script_path} --vault '{vault_str}' rebuild-meta")


def layered_recall(
    query: str,
    project_vault: Path | None = None,
    personal_vault: Path | None = None,
    page_type: str | None = None,
    tag: str | None = None,
    limit: int = 10,
    scope: str = "all",
) -> list[dict[str, Any]]:
    """
    Search both personal vault (~/.llm-wiki) and project vault.
    Supports multi-token term matching and exact substring bonuses.
    Returns deduplicated scored items tagged with 📁 project or 📓 personal.
    """
    candidates: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    vaults_to_search: list[tuple[Path, str]] = []
    if scope in ("all", "project") and project_vault and project_vault.exists():
        vaults_to_search.append((project_vault, "project"))
    if scope in ("all", "personal") and personal_vault and personal_vault.exists():
        vaults_to_search.append((personal_vault, "personal"))

    q_lower = query.lower().strip() if query else ""
    tokens = [tok for tok in q_lower.split() if tok]

    for vpath, vscope in vaults_to_search:
        pages = scan_vault_pages(vpath)
        for rel_str, pinfo in pages.items():
            pid = pinfo["id"]
            if pid in seen_ids:
                continue

            # Type filter
            if page_type and pinfo["type"].lower() != page_type.lower():
                continue

            # Tag filter
            if tag:
                ptags = [t.lower() for t in pinfo["tags"]]
                if tag.lower() not in ptags:
                    continue

            # Scoring calculation
            score = 0
            title = pinfo["title"]
            body = pinfo["body"]
            summary = pinfo["summary"]

            pid_l = pid.lower()
            title_l = title.lower()
            summary_l = summary.lower()
            body_l = body.lower()
            aliases_l = [a.lower() for a in pinfo["aliases"]]
            tags_l = [t.lower() for t in pinfo["tags"]]

            if not q_lower:
                score = 1
            else:
                # 1. Whole query match
                if q_lower == pid_l:
                    score += 150
                elif q_lower in pid_l:
                    score += 60

                if q_lower == title_l:
                    score += 120
                elif q_lower in title_l:
                    score += 50

                for a in aliases_l:
                    if q_lower == a:
                        score += 100
                    elif q_lower in a:
                        score += 40

                for t in tags_l:
                    if q_lower == t:
                        score += 50
                    elif q_lower in t:
                        score += 25

                if q_lower in summary_l:
                    score += 35
                if q_lower in body_l:
                    score += 15

                # 2. Multi-token match (when query contains multiple terms)
                if len(tokens) > 1:
                    matched_tokens = 0
                    for tok in tokens:
                        tok_matched = False
                        if tok in pid_l:
                            score += 20
                            tok_matched = True
                        if tok in title_l:
                            score += 25
                            tok_matched = True
                        for a in aliases_l:
                            if tok in a:
                                score += 15
                                tok_matched = True
                        for t in tags_l:
                            if tok in t:
                                score += 15
                                tok_matched = True
                        if tok in summary_l:
                            score += 15
                            tok_matched = True
                        if tok in body_l:
                            score += 8
                            tok_matched = True
                        if tok_matched:
                            matched_tokens += 1
                    if matched_tokens == len(tokens):
                        score += 40

            if score > 0:
                seen_ids.add(pid)
                candidates.append({
                    "score": score,
                    "scope": vscope,
                    "vault": str(vpath),
                    "rel_path": rel_str,
                    "abs_path": str(pinfo["path"]),
                    "id": pid,
                    "title": title,
                    "type": pinfo["type"],
                    "status": pinfo["status"],
                    "summary": summary,
                    "tags": pinfo["tags"],
                    "updated": pinfo["updated"],
                })

    candidates.sort(key=lambda x: x["score"], reverse=True)
    return candidates[:limit]


def print_status_dashboard(project_vault: Path | None, personal_vault: Path | None) -> None:
    """Print an ASCII operational status dashboard for layered vaults."""
    print("=" * 68)
    print("           LLM Wiki Knowledge Engine Dashboard (OKF v0.2)        ")
    print("=" * 68)

    pv_str = str(personal_vault) if personal_vault and personal_vault.exists() else "Not initialized (run: wiki_tool.py init --personal)"
    print(f"🏠 Personal Vault : {pv_str}")

    prj_str = str(project_vault) if project_vault and project_vault.exists() else "None found (run: wiki_tool.py init)"
    print(f"📁 Project Vault  : {prj_str}")
    print("-" * 68)

    active_vault = project_vault if (project_vault and project_vault.exists()) else personal_vault
    if not active_vault or not active_vault.exists():
        print("No active wiki vault found. Initialize one using 'wiki_tool.py init'.")
        print("=" * 68)
        return

    pages = scan_vault_pages(active_vault)
    type_counts: dict[str, int] = {}
    for p in pages.values():
        type_counts[p["type"]] = type_counts.get(p["type"], 0) + 1

    print(f"Total Knowledge Pages: {len(pages)}")
    print(f"  - Concepts       (CON)   : {type_counts.get('concept', 0)}")
    print(f"  - Entities       (ENT)   : {type_counts.get('entity', 0)}")
    print(f"  - Synthesis      (SYN)   : {type_counts.get('synthesis', 0)}")
    print(f"  - Retrospectives (RETRO) : {type_counts.get('retro', 0)}")
    print(f"  - Trajectories   (TRAJ)  : {type_counts.get('trajectory', 0)}")
    print(f"  - Reusable Skills(SKILL) : {type_counts.get('skill', 0)}")
    print(f"  - Source Packets (SRC)   : {type_counts.get('source', 0)}")
    print(f"  - Other Pages            : {type_counts.get('other', 0)}")
    print("-" * 68)

    lint_res = lint_vault(active_vault, auto_fix=False)
    print(f"Health Status: {'[HEALTHY]' if lint_res['passed'] else '[ATTENTION NEEDED]'}")
    print(f"  - Broken Links     : {len(lint_res['broken_links'])}")
    print(f"  - Orphan Pages     : {len(lint_res['orphans'])}")
    print(f"  - Frontmatter Errs : {len(lint_res['frontmatter_errors'])}")
    print(f"  - Unindexed Pages  : {len(lint_res['unindexed_pages'])}")
    print("-" * 68)

    sorted_pages = sorted(pages.values(), key=lambda x: x["updated"], reverse=True)[:5]
    print("Recent Activity / Latest Additions:")
    for p in sorted_pages:
        print(f"  [{p['type']:<10}] {p['id']} - {p['title']} ({p['updated']})")
    print("=" * 68)


def main():
    parser = argparse.ArgumentParser(description="LLM Wiki Knowledge Compounding & Agent Memory Engine (OKF v0.2)")
    parser.add_argument("--vault", "-V", type=str, help="Explicit path to wiki vault (or via WIKI_ROOT env)")

    subparsers = parser.add_subparsers(dest="command", required=True)

    # 1. init
    p_init = subparsers.add_parser("init", help="Initialize a wiki vault")
    p_init.add_argument("--target", "-t", type=str, help="Target directory for wiki")
    p_init.add_argument("--personal", action="store_true", help="Initialize personal vault at ~/.llm-wiki")

    # 2. capture
    p_cap = subparsers.add_parser("capture", help="Capture raw source into immutable source packet")
    p_cap.add_argument("--title", required=True, help="Title of the source")
    p_cap.add_argument("--file", "-f", type=str, help="Source file path to read")
    p_cap.add_argument("--text", type=str, help="Direct text content to capture")
    p_cap.add_argument("--url", type=str, help="Source URL")
    p_cap.add_argument("--tags", type=str, help="Comma-separated tags")
    p_cap.add_argument("--summary", type=str, help="Summary of source")

    # 3. retro
    p_retro = subparsers.add_parser("retro", help="Record atomic insight / post-task retrospective")
    p_retro.add_argument("--title", required=True, help="Insight title")
    p_retro.add_argument("--insight", required=True, help="Core insight / lesson learned")
    p_retro.add_argument("--task-slice", type=str, default="", help="Originating TaskSlice ID")
    p_retro.add_argument("--context", type=str, default="", help="Context & background")
    p_retro.add_argument("--tags", type=str, help="Comma-separated tags")
    p_retro.add_argument("--summary", type=str, help="Short summary")

    # 4. observe
    p_obs = subparsers.add_parser("observe", help="Append session observation to meta/observations.md")
    p_obs.add_argument("--text", required=True, help="Observation text")
    p_obs.add_argument("--author", type=str, default="Agent", help="Agent identifier")
    p_obs.add_argument("--tags", type=str, help="Comma-separated tags")

    # 5. record-trajectory
    p_traj = subparsers.add_parser("record-trajectory", help="Record agent problem-solving trajectory")
    p_traj.add_argument("--title", required=True, help="Trajectory title")
    p_traj.add_argument("--objective", required=True, help="Task objective")
    p_traj.add_argument("--steps", required=True, help="Step-by-step tool execution notes")
    p_traj.add_argument("--task-slice", type=str, default="", help="TaskSlice ID")
    p_traj.add_argument("--bottlenecks", type=str, default="", help="Hurdles or errors encountered")
    p_traj.add_argument("--breakthrough", type=str, default="", help="Breakthrough or key fix")
    p_traj.add_argument("--outcome", type=str, default="", help="Final outcome")
    p_traj.add_argument("--tags", type=str, help="Comma-separated tags")
    p_traj.add_argument("--summary", type=str, help="Short summary")

    # 6. distill-skill
    p_dist = subparsers.add_parser("distill-skill", help="Distill trajectories into a reusable skill/playbook")
    p_dist.add_argument("--title", required=True, help="Skill title")
    p_dist.add_argument("--pattern", required=True, help="Proven solution pattern")
    p_dist.add_argument("--trajectories", required=True, help="Comma-separated trajectory IDs (e.g. TRAJ-20260914-0001)")
    p_dist.add_argument("--antipatterns", type=str, default="", help="Pitfalls to avoid")
    p_dist.add_argument("--checklist", type=str, help="Comma-separated verification items")
    p_dist.add_argument("--tags", type=str, help="Comma-separated tags")
    p_dist.add_argument("--summary", type=str, help="Short summary")

    # 7. ensure-page (pi-llm-wiki parity)
    p_ens = subparsers.add_parser("ensure-page", help="Resolve or safely create an entity/concept/synthesis page")
    p_ens.add_argument("--type", required=True, choices=["concept", "entity", "synthesis", "retro", "trajectory", "skill", "source"], help="Page type")
    p_ens.add_argument("--title", required=True, help="Page title")
    p_ens.add_argument("--id", type=str, help="Explicit stable ID")
    p_ens.add_argument("--content", type=str, default="", help="Markdown body content")
    p_ens.add_argument("--tags", type=str, help="Comma-separated tags")
    p_ens.add_argument("--aliases", type=str, help="Comma-separated aliases")
    p_ens.add_argument("--summary", type=str, default="", help="One-line summary")
    p_ens.add_argument("--sources", type=str, help="Comma-separated source IDs")

    # 8. ingest (pi-llm-wiki parity)
    p_ing = subparsers.add_parser("ingest", help="Batch process uningested source packets into wiki pages")
    p_ing.add_argument("--source", type=str, help="Specific source ID to ingest (optional)")

    # 9. search (pi-llm-wiki parity)
    p_srch = subparsers.add_parser("search", help="Search wiki registry directly")
    p_srch.add_argument("query", nargs="?", default="", help="Search query")
    p_srch.add_argument("--json", action="store_true", help="Output raw JSON")

    # 10. watch (pi-llm-wiki parity)
    p_wtch = subparsers.add_parser("watch", help="Print crontab line for automated wiki maintenance")
    p_wtch.add_argument("--schedule", choices=["hourly", "daily", "weekly"], default="daily", help="Maintenance frequency")

    # 11. recall
    p_rec = subparsers.add_parser("recall", help="Layered recall across personal and project vaults")
    p_rec.add_argument("query", nargs="?", default="", help="Search query / keyword")
    p_rec.add_argument("--type", type=str, help="Filter by page type (concept, entity, retro, skill, etc.)")
    p_rec.add_argument("--tag", type=str, help="Filter by tag")
    p_rec.add_argument("--limit", type=int, default=10, help="Max results")
    p_rec.add_argument("--scope", choices=["all", "project", "personal"], default="all", help="Search scope")
    p_rec.add_argument("--json", action="store_true", help="Output raw JSON")

    # 12. recall-skill
    p_rec_sk = subparsers.add_parser("recall-skill", help="Recall distilled skills & playbooks")
    p_rec_sk.add_argument("query", nargs="?", default="", help="Skill query")
    p_rec_sk.add_argument("--limit", type=int, default=10, help="Max results")
    p_rec_sk.add_argument("--json", action="store_true", help="Output raw JSON")

    # 13. lint
    p_lint = subparsers.add_parser("lint", help="Mechanical linting (broken links, orphans, schema)")
    p_lint.add_argument("--fix", action="store_true", help="Auto-rebuild metadata index if unindexed pages exist")

    # 14. rebuild-meta
    p_reb = subparsers.add_parser("rebuild-meta", help="Force full rebuild of index.md, backlinks, and registry")

    # 15. status
    subparsers.add_parser("status", help="Show operational dashboard")

    args = parser.parse_args()

    # Determine target vault
    project_vault = Path(args.vault).resolve() if args.vault else resolve_project_vault()
    personal_vault = resolve_personal_vault()

    try:
        if args.command == "init":
            if args.personal:
                target = personal_vault
                is_pers = True
            elif args.target:
                target = Path(args.target).resolve()
                is_pers = False
            elif project_vault:
                target = project_vault
                is_pers = False
            else:
                target = Path.cwd() / "05_研究资产" / "wiki"
                is_pers = False

            init_vault(target, is_personal=is_pers)
            print(f"[✔] Initialized OKF v0.2 Wiki Vault at {target}")
            return

        # For commands operating on an active vault:
        active_vault = project_vault or (personal_vault if personal_vault.exists() else None)
        if not active_vault and args.command not in ("recall", "recall-skill", "status"):
            active_vault = Path.cwd() / "05_研究资产" / "wiki"
            init_vault(active_vault)

        if args.command == "capture":
            tags = [t.strip() for t in args.tags.split(",")] if args.tags else []
            if args.file:
                fpath = Path(args.file).resolve()
                content = fpath.read_text(encoding="utf-8")
                loc = str(fpath)
                stype = "file"
            elif args.url:
                content = args.text or f"URL Reference: {args.url}"
                loc = args.url
                stype = "url"
            elif args.text:
                content = args.text
                loc = "pasted_text"
                stype = "text"
            else:
                print("[FAIL] One of --file, --url, or --text is required", file=sys.stderr)
                sys.exit(1)

            dest = capture_source(
                vault=active_vault,
                title=args.title,
                source_location=loc,
                content=content,
                source_type=stype,
                tags=tags,
                summary=args.summary or "",
            )
            print(f"[✔] Captured source packet: {dest.name}")

        elif args.command == "retro":
            tags = [t.strip() for t in args.tags.split(",")] if args.tags else []
            dest = record_retro(
                vault=active_vault,
                title=args.title,
                insight=args.insight,
                task_slice=args.task_slice,
                context=args.context,
                tags=tags,
                summary=args.summary or "",
            )
            print(f"[✔] Recorded atomic retro insight: {dest.name}")

        elif args.command == "observe":
            tags = [t.strip() for t in args.tags.split(",")] if args.tags else []
            append_observation(active_vault, text=args.text, author=args.author, tags=tags)
            print(f"[✔] Recorded session observation in {active_vault / 'meta/observations.md'}")

        elif args.command == "record-trajectory":
            tags = [t.strip() for t in args.tags.split(",")] if args.tags else []
            dest = record_trajectory(
                vault=active_vault,
                title=args.title,
                objective=args.objective,
                steps=args.steps,
                task_slice=args.task_slice,
                bottlenecks=args.bottlenecks,
                breakthrough=args.breakthrough,
                outcome=args.outcome,
                tags=tags,
                summary=args.summary or "",
            )
            print(f"[✔] Recorded agent problem-solving trajectory: {dest.name}")

        elif args.command == "distill-skill":
            tags = [t.strip() for t in args.tags.split(",")] if args.tags else []
            check_items = [c.strip() for c in args.checklist.split(",")] if args.checklist else None
            trajs = [t.strip() for t in args.trajectories.split(",") if t.strip()]
            dest = distill_skill(
                vault=active_vault,
                title=args.title,
                pattern=args.pattern,
                trajectories=trajs,
                antipatterns=args.antipatterns,
                checklist=check_items,
                tags=tags,
                summary=args.summary or "",
            )
            print(f"[✔] Distilled reusable skill: {dest.name}")

        elif args.command == "ensure-page":
            tags = [t.strip() for t in args.tags.split(",")] if args.tags else []
            aliases = [a.strip() for a in args.aliases.split(",")] if args.aliases else []
            sources = [s.strip() for s in args.sources.split(",")] if args.sources else []
            dest, created = ensure_page(
                vault=active_vault,
                page_type=args.type,
                title=args.title,
                page_id=args.id,
                content=args.content,
                tags=tags,
                aliases=aliases,
                summary=args.summary,
                sources=sources,
            )
            action_desc = "Created new" if created else "Resolved existing"
            print(f"[✔] {action_desc} {args.type} page: {dest.name} (`{dest.stem}`)")

        elif args.command == "ingest":
            ingested = ingest_sources(vault=active_vault, source_id=args.source)
            print(f"[*] Ingested {len(ingested)} source packet(s):")
            for item in ingested:
                print(f"  - {item['source_id']} -> {item['synthesis_page']} ({'new' if item['created'] else 'linked'})")

        elif args.command == "search":
            results = search_registry(vault=active_vault, query=args.query)
            if args.json:
                print(json.dumps(results, indent=2, ensure_ascii=False))
                return
            print(f"[*] Search Registry Query: '{args.query}' (Found {len(results)} matches)")
            for idx, r in enumerate(results, 1):
                tags_str = f" [{', '.join(r['tags'])}]" if r["tags"] else ""
                print(f"{idx}. [[{r['rel_path']}|{r['title']}]] (`{r['id']}`) - Type: {r['type']}{tags_str}")
                if r["summary"]:
                    print(f"   Summary: {r['summary']}")

        elif args.command == "watch":
            print_watch_schedule(vault=active_vault, schedule=args.schedule)

        elif args.command == "recall":
            results = layered_recall(
                query=args.query,
                project_vault=project_vault,
                personal_vault=personal_vault,
                page_type=args.type,
                tag=args.tag,
                limit=args.limit,
                scope=args.scope,
            )
            if args.json:
                print(json.dumps(results, indent=2, ensure_ascii=False))
                return

            print(f"[*] Layered Recall Query: '{args.query}' (Found {len(results)} matches)")
            for idx, r in enumerate(results, 1):
                tag_label = "📁 project" if r["scope"] == "project" else "📓 personal"
                tags_str = f" [{', '.join(r['tags'])}]" if r["tags"] else ""
                print(f"\n{idx}. {tag_label} | [[{r['rel_path']}|{r['title']}]] (`{r['id']}`) - Type: {r['type']}{tags_str}")
                if r["summary"]:
                    print(f"   Summary: {r['summary']}")
                print(f"   Path: {r['abs_path']}")

        elif args.command == "recall-skill":
            results = layered_recall(
                query=args.query,
                project_vault=project_vault,
                personal_vault=personal_vault,
                page_type="skill",
                limit=args.limit,
                scope="all",
            )
            if args.json:
                print(json.dumps(results, indent=2, ensure_ascii=False))
                return
            print(f"[*] Recalled {len(results)} Distilled Skill(s) for '{args.query}':")
            for idx, r in enumerate(results, 1):
                tag_label = "📁 project" if r["scope"] == "project" else "📓 personal"
                print(f"\n{idx}. {tag_label} | [[{r['rel_path']}|{r['title']}]] (`{r['id']}`)")
                if r["summary"]:
                    print(f"   Summary: {r['summary']}")
                print(f"   Path: {r['abs_path']}")

        elif args.command == "lint":
            res = lint_vault(active_vault, auto_fix=args.fix)
            print(f"[*] Lint Report for {active_vault}:")
            print(f"  - Scanned pages: {res['total_pages_scanned']}")
            print(f"  - Broken links:  {len(res['broken_links'])}")
            for b in res["broken_links"]:
                print(f"    ❌ In {b['source']} -> Target '{b['target']}' not found")
            print(f"  - Orphan pages:  {len(res['orphans'])}")
            for o in res["orphans"]:
                print(f"    ⚠️ Orphan page: {o}")
            print(f"  - Frontmatter errors: {len(res['frontmatter_errors'])}")
            for e in res["frontmatter_errors"]:
                print(f"    ❌ {e['file']}: {e['error']}")
            if res["duplicate_ids"]:
                print(f"  - Duplicate IDs: {len(res['duplicate_ids'])}")
                for pid, files in res["duplicate_ids"].items():
                    print(f"    ❌ Duplicate ID '{pid}' in: {', '.join(files)}")
            if res["duplicate_aliases"]:
                print(f"  - Duplicate Aliases: {len(res['duplicate_aliases'])}")
                for a, files in res["duplicate_aliases"].items():
                    print(f"    ❌ Duplicate Alias '{a}' in: {', '.join(files)}")
            print(f"  - Unindexed pages: {len(res['unindexed_pages'])}")
            for u in res["unindexed_pages"]:
                print(f"    ⚠️ Unindexed: {u}")

            if res["passed"]:
                print("[✔] Wiki vault lint PASSED with zero defects.")
                sys.exit(0)
            else:
                print("[FAIL] Wiki vault lint failed with issues.")
                sys.exit(1)

        elif args.command == "rebuild-meta":
            res = rebuild_metadata(active_vault)
            print(f"[✔] Rebuilt metadata projections for {active_vault}:")
            print(f"  - Total indexed pages: {res['total_pages']}")
            print(f"  - Backlinks indexed:   {res['backlinks_count']}")
            print(f"  - Index updated at:    {active_vault / 'meta/index.md'}")

        elif args.command == "status":
            print_status_dashboard(project_vault=project_vault, personal_vault=personal_vault)

    except PermissionError as pe:
        print(f"[FAIL] Permission denied: {pe}", file=sys.stderr)
        sys.exit(1)
    except OSError as oe:
        print(f"[FAIL] OS Error: {oe}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
