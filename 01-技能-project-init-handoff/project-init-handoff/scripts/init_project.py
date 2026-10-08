#!/usr/bin/env python3
"""
init_project.py - Standardized Project Initialization Script
Derived directly from R-ICL's decuple architecture and governance canon.

Profiles:
  1. r-icl / research (default): Full 10-layer numbered architecture (00_入口 ~ 09_提案与草稿)
     with 05_研究资产 (raw, evidence, snapshots, claims, reports),
     09_提案与草稿 (task_slices, experiment_specs, definitions, claims, evidence, mutation_requests),
     complete governance contracts (G-001~G-014, fail_closed, INV-001~INV-017),
     4 JSON Schemas, and 12 core object templates.
  2. engineering: 10-layer architecture using 05_资产库 and 09_提案与草稿/proposals
     for production software systems.
  3. agile: Streamlined agile structure (docs, src, tests, tasks, 07_运行记录, templates)
     for lightweight tooling.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

try:
    from wiki_tool import init_vault
except ImportError:
    _script_dir = Path(__file__).resolve().parent
    if str(_script_dir) not in sys.path:
        sys.path.insert(0, str(_script_dir))
    from wiki_tool import init_vault


def compute_sha256(filepath: Path) -> str:
    """Compute SHA-256 hash of a file."""
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def detect_environment() -> dict[str, str]:
    """Detect local runtime versions and environment metadata."""
    env_info = {
        "os": f"{platform.system()} {platform.release()} ({platform.machine()})",
        "python": platform.python_version(),
        "git": "not available",
        "node": "not available",
    }
    try:
        git_res = subprocess.run(["git", "--version"], capture_output=True, text=True, timeout=5)
        if git_res.returncode == 0:
            env_info["git"] = git_res.stdout.strip()
    except Exception:
        pass

    try:
        node_res = subprocess.run(["node", "--version"], capture_output=True, text=True, timeout=5)
        if node_res.returncode == 0:
            env_info["node"] = node_res.stdout.strip()
    except Exception:
        pass

    return env_info


def get_decuple_dirs(profile: str = "r-icl") -> list[str]:
    is_research = profile in ("r-icl", "research")
    layer_05 = "05_研究资产" if is_research else "05_资产库"

    dirs = [
        "00_入口",
        "01_需求与验收",
        "02_架构与合同",
        "02_架构与合同/schemas",
        "03_实现",
        "03_实现/core",
        "03_实现/plugins",
        "03_实现/adapters",
        "03_实现/cli",
        "03_实现/workspaces",
        "04_测试与验收",
        "04_测试与验收/fixtures",
        layer_05,
        f"{layer_05}/raw",
        f"{layer_05}/evidence",
        f"{layer_05}/snapshots",
        f"{layer_05}/claims",
        f"{layer_05}/reports",
        f"{layer_05}/wiki",
        f"{layer_05}/wiki/concepts",
        f"{layer_05}/wiki/entities",
        f"{layer_05}/wiki/synthesis",
        f"{layer_05}/wiki/retro",
        f"{layer_05}/wiki/trajectories",
        f"{layer_05}/wiki/skills",
        f"{layer_05}/wiki/sources",
        f"{layer_05}/wiki/meta",
        "06_任务与交接",
        "06_任务与交接/active",
        "06_任务与交接/completed",
        "06_任务与交接/records",
        "06_任务与交接/handoffs",
        "07_运行记录",
        "07_运行记录/runs",
        "07_运行记录/artifacts",
        "08_归档",
        "08_归档/superseded",
        "08_归档/failed",
        "09_提案与草稿",
        "09_提案与草稿/task_slices",
        "templates",
    ]

    if is_research:
        dirs.extend([
            "09_提案与草稿/experiment_specs",
            "09_提案与草稿/definitions",
            "09_提案与草稿/claims",
            "09_提案与草稿/evidence",
            "09_提案与草稿/mutation_requests",
        ])
    else:
        dirs.append("09_提案与草稿/proposals")

    return dirs


AGILE_DIRS = [
    "docs",
    "src",
    "tests",
    "tasks/active",
    "tasks/completed",
    "tasks/records",
    "tasks/handoffs",
    "07_运行记录",
    ".llm-wiki",
    "templates",
]


def init_decuple_project(
    target_dir: Path,
    project_name: str,
    author: str,
    resources_dir: Path | None,
    profile: str = "r-icl",
    skip_contracts: bool = False,
    dry_run: bool = False,
):
    today = datetime.date.today().isoformat()
    env = detect_environment()
    dirs = get_decuple_dirs(profile)
    layer_05_name = "05_研究资产" if profile in ("r-icl", "research") else "05_资产库"

    print(f"[*] Initializing Decuple Project: '{project_name}' at {target_dir}")
    print(f"[*] Profile: {profile} (Layer 05: {layer_05_name})")
    print(f"[*] Environment: OS={env['os']}, Python={env['python']}, Git={env['git']}, Node={env['node']}")

    if dry_run:
        print("[DRY-RUN] Will create directories:")
        for d in dirs:
            print(f"  + {target_dir / d}")
        return

    # 1. Create directory hierarchy
    for d in dirs:
        (target_dir / d).mkdir(parents=True, exist_ok=True)

    # 2. Copy Templates (ONLY object templates from resources/templates)
    if resources_dir and (resources_dir / "templates").exists():
        templates_dest = target_dir / "templates"
        for item in (resources_dir / "templates").glob("*.md"):
            shutil.copy2(item, templates_dest / item.name)

    # 3. Copy JSON Schemas to 02_架构与合同/schemas/
    if resources_dir and (resources_dir / "schemas").exists():
        schemas_dest = target_dir / "02_架构与合同" / "schemas"
        for item in (resources_dir / "schemas").glob("*.json"):
            shutil.copy2(item, schemas_dest / item.name)

    # 4. Copy Baseline Contracts to 01_需求与验收 and 02_架构与合同
    if not skip_contracts and resources_dir and (resources_dir / "contracts").exists():
        contracts_src = resources_dir / "contracts"
        # 01 contracts
        for c in ["05_Gate清单与批准边界.md", "06_数据边界.md", "07_错误处置与fail_closed.md", "08_共享执行与审核合同.md"]:
            if (contracts_src / c).exists() and not (target_dir / "01_需求与验收" / c).exists():
                shutil.copy2(contracts_src / c, target_dir / "01_需求与验收" / c)
        # 02 contracts
        for c in ["01_实体与版本合同.md", "02_TaskSlice与Handoff合同.md", "04_可执行不变量.md"]:
            if (contracts_src / c).exists() and not (target_dir / "02_架构与合同" / c).exists():
                shutil.copy2(contracts_src / c, target_dir / "02_架构与合同" / c)

    # 4.5 Initialize OKF v0.2 Wiki Vault inside layer_05
    wiki_path = target_dir / layer_05_name / "wiki"
    try:
        init_vault(wiki_path, is_personal=False)
    except Exception as e:
        print(f"[!] Warning: failed to auto-init wiki vault: {e}")

    # 5. Create Root AGENTS.md
    agents_path = target_dir / "AGENTS.md"
    if not agents_path.exists():
        agents_content = f"""# AGENTS.md

本文件适用于整个 {project_name} 工程目录。

## 每次会话启动必须执行

1. 读取 `README.md`。
2. 读取 `00_入口/00_当前.md`（全库唯一权威物理当前状态）。
3. 读取根目录 `HANDOFF.md`（全库唯一当前全局交接）。
4. 读取 `06_任务与交接/active/` 中的在轨活跃目标任务切片。
5. 修改文件前检查同目录现有内容与活动引用链接。

## 当前阶段

当前为 P0 初始化基线阶段。除非用户另行明确批准：
- 只完善需求、边界、合同、测试与实施计划；
- 不在主分支编写未经批准的生产实现；
- 不擅自引入未经登记的外部依赖或真实生产/敏感数据；
- 不随意变更既有技术架构基线。

## 四方权力边界体系

- **用户 (Human Owner)**: 产品/科研目标、实质授权、人类验收和业务/科学边界的最终负责人。
- **主协调 Agent (Coordinator)**: 拆任务切片、渲染派发交接包、独立复算 SHA-256、整合证据、暴露待决问题；**严禁自我批准**！
- **实现 Agent (Implementation Worker - IMPL)**: 严格按已冻结的任务包在允许路径白名单内实现；只能写自己的 attempt workspace，产出候选版本；**严禁直接写入 canonical 生产目录**。
- **审核 Agent (Validation Auditor - VAL)**: 独立责任视角，只读冻结合同与候选版本，在独立 workspace 执行盲审与交叉核对；只输出封闭工程判定，**严禁替代人类验收**。

## 单事实源准则

- **全库唯一当前**：`00_入口/00_当前.md`。
- **全库唯一过程日志**：`07_运行记录/LOG.md`（纯追加 append-only，严禁篡改或重排历史行，更正用 `CORRECTION`）。
- **全库唯一当前交接**：根目录 `HANDOFF.md`；历史交接归档于 `06_任务与交接/handoffs/`。
- **暂存隔离原则**：未经 Gate 批准的提案与草稿统一入 `09_提案与草稿/`，严禁未经批准直接落入 canonical 生产目录。
- **不可变凭据保留**：HandoffBundle 与 ResultBundle 归档于 `06_任务与交接/records/<task_slice_id>/<attempt_id>/`，被拒绝的尝试亦必须永久保留留痕。

## 六级状态词分离协议

必须严格区分以下六级状态，绝对不可相互混淆或替代：
- `proposed`: 已提出，未批准。
- `approved`: 用户或相应 Gate 已批准进入下一阶段。
- `implemented`: 候选代码或产物已生成于 workspace。
- `tested`: 自动化机器测试已全部通过。
- `human-accepted`: 用户已完成真实交互、功能审查或场景使用验收。
- `scientifically-supported` (或 `verified-in-prod`): 结论已获确凿证据链充分支撑。

**警示**：工具返回成功 (exit code 0)、文件存在或测试通过，**绝对不等于**用户验收或业务结论成立！

## 审核判定封闭词表 (Validation Verdicts)

审核 Worker 的 ResultBundle 判定必须且仅限以下四词：
- `CONFORMANT`: 按冻结合同与候选 SHA 完成复算与测试，未发现工程偏差。
- `DEVIATIONS_FOUND`: 发现偏差、绕过或缺口，并附清单与复现依据。
- `INCOMPLETE`: 审核无法完成（如候选 SHA 漂移、环境缺失或输入不完整）。
- `OUT_OF_SCOPE`: 发现超出当前任务切片范围的事项，转协调方或用户处置。

## 沙箱与两阶段入库规范 (Promotion Plan)

- 库根只读 + 白名单写入面。
- Worker 只能写自己的 `03_实现/workspaces/<task_slice_id>/<attempt_id>/` 和受控 ResultBundle 提交通道。
- 严禁在工程中保存任何明文密钥、API Token、密码或未经脱敏的真实敏感数据。
- 候选成果必须先在 workspace 交付，经协调方复算、审核方验证出具 `CONFORMANT`，并由用户下发明确入库指令后，方可由协调方原子执行 Canonical Bootstrap 晋升入库。

## 错误处置与 Fail-Closed 原则

- **提交前违规 / 校验失败**：立即触发 `fail_closed`，全库 canonical 零写入，并在 `07_运行记录/LOG.md` 追加拒绝留痕。
- **提交后状态撕裂**：触发 `needs_reconcile`，阻断下游依赖并等待人工介入。
- **上游版本变更**：标记 `stale/needs_review`，不自动否定。
- **可恢复失败**：通过人工发起新 attempt 进行 `retry`，保留旧历史。

## 极小化交接消息协议

交接交互消息只传递五元组：
1. 文件路径 (`bundle_path`)；
2. 校验哈希 (`SHA-256`)；
3. 状态指针 (`state_pointer`)；
4. 发送方 (`sender`)；
5. 接收方 (`intended_receiver`)。

完整任务、结果和说明必须完全落入 `TaskSlice`、`ResultBundle` 或 `HandoffBundle` 物理文件中。

## 知识复利与工作记忆守则 (Compounding Wiki & Working Memory)

- 本工程集成 Andrej Karpathy LLM Wiki 模式与 OKF v0.2 标准。知识库位于 `{layer_05_name}/wiki/`。
- **任务终结必复盘 (`wiki_retro`)**: 任务切片完成或阶段交接时，必须提炼 1-2 条原子洞察沉淀至 `wiki/retro/`，杜绝知识随会话丢失。
- **障碍求解记轨迹 (`wiki_record_trajectory`)**: 遇到复杂排障、环境冲突或方案突破时，记录工具调用与推演步骤；后续提炼为 `wiki/skills/` 通用范式。
- **双层知识召回 (`wiki_recall`)**: 接手新任务或排查疑难时，使用 `wiki_tool.py recall` 分层检索个人知识库 (`~/.llm-wiki`) 与项目知识库。
"""
        agents_path.write_text(agents_content, encoding="utf-8")

    # 6. Create Root README.md
    readme_path = target_dir / "README.md"
    if not readme_path.exists():
        readme_content = f"""---
type: project-index
status: active
created: {today}
updated: {today}
---

# {project_name}

本工程采用基于 R-ICL 演进的标准十进制分层工程架构与多 Agent 协作治理规范，并原生集成 OKF v0.2 LLM Wiki 知识复利层。

## 启动阅读顺序

1. `00_入口/00_当前.md`（全库唯一权威当前状态）
2. `HANDOFF.md`（当前全局交接入口）
3. `AGENTS.md`（行为规范与权力边界守则）
4. `01_需求与验收/00_索引.md` 与 `02_架构与合同/00_索引.md`
5. `{layer_05_name}/wiki/meta/index.md`（知识库总索引）
6. `06_任务与交接/active/`（当前目标任务）

## 十进制分层目录职责

| 目录 | 责任定义 |
|---|---|
| `00_入口` | 全库唯一当前、路线图规划、决策沉淀 (DEC)、开放问题与风险 (Q) |
| `01_需求与验收` | 用户故事、范围与非目标、验收矩阵、失败场景 (F)、分级 Gate (G-001~G-014)、数据边界、错误处置、共享合同 |
| `02_架构与合同` | 系统方案基线、实体与版本合同、TaskSlice与交接合同、可执行不变量 (INV-001~INV-017)、JSON Schemas |
| `03_实现` | 正确性内核 (Core)、插件/适配器 (Plugins/Adapters)、CLI 工具、隔离沙箱工作区 (workspaces/) |
| `04_测试与验收` | 分层测试策略、契约测试、人类验收脚本、可重现测试输入 (fixtures/) |
| `{layer_05_name}` | 原始数据 (raw)、证据卡 (evidence)、快照 (snapshots)、主张 (claims)、报告 (reports)、LLM-Wiki 知识库 (wiki/) |
| `06_任务与交接` | active 在轨切片、completed 已归档切片、records 不变凭据包、handoffs 历史交接 |
| `07_运行记录` | LOG.md 全库唯一纯追加过程流水账、runs 执行记录、artifacts 运行产物指针 |
| `08_归档` | superseded 已废弃资产、failed 失败尝试记录（永不物理删除） |
| `09_提案与草稿` | Gate 批准前唯一的 proposal/draft 隔离暂存区（严禁污染 canonical） |
| `templates` | 治理对象、任务切片、交接信封、结果凭据与 OKF v0.2 Wiki 标准不可变模板库 |
"""
        readme_path.write_text(readme_content, encoding="utf-8")

    # 7. Create 00_入口 files
    curr_path = target_dir / "00_入口" / "00_当前.md"
    if not curr_path.exists():
        curr_content = f"""---
type: current
status: active
phase: P0
updated: {today}
---

# 当前

本文件是本工程全库唯一的权威物理当前状态入口。

## 现在 (Now)

工程基础骨架、AGENTS 治理准则、HANDOFF 交接基线与 07_运行记录/LOG 过程流水账已完成初始化。当前处于 P0 初始化基线阶段。

当前已完成：
- [x] 十进制工程目录层级结构初始化
- [x] AGENTS.md 治理边界与状态词分离规范确立
- [x] 全库唯一过程日志 `07_运行记录/LOG.md` 建立并登记 `PROC-0001 BOOTSTRAP`
- [x] 根目录 `HANDOFF.md` 全局基线就绪
- [x] 核心对象模板库与 JSON Schema 就位
- [x] 治理门禁与可执行不变量基线就绪
- [x] LLM-Wiki 知识库与工作记忆层 ({layer_05_name}/wiki/) 初始化就绪

当前尚未完成：
- [ ] 业务/科研需求与范围边界冻结
- [ ] 系统技术架构合同与可执行不变量人工确认
- [ ] 第一个任务切片 (TS-001) 规划与 Gate 批准

## 已确认的关键决策

- **DEC-0001** ({today}): 工程初始化采用标准十进制分层架构与单事实源治理体系。

## 当前唯一下一步 (Sole Next Action)

完善 `01_需求与验收` 中的用户故事与范围边界，由主协调方起草第一批架构合同与任务切片。

## 主要入口链接

- `README.md`
- `HANDOFF.md`
- `AGENTS.md`
- `07_运行记录/LOG.md`
- `{layer_05_name}/wiki/meta/index.md`
"""
        curr_path.write_text(curr_content, encoding="utf-8")

    roadmap_path = target_dir / "00_入口" / "01_路线图.md"
    if not roadmap_path.exists():
        roadmap_content = f"""---
type: roadmap
status: active
updated: {today}
---

# 路线图

## 阶段规划

- **P0 基线阶段** (当前): 架构骨架、权力边界、治理门禁、不可变模板与可执行不变量冻结。
- **P1 核心能力构建**: 最小闭环任务切片实现、独立工程审核与首次两阶段交付入库。
- **P2 端到端集成**: 完整多切片调度、运行时沙箱增强与自动化验证演练。
- **P3 生产应用与长期维护**: 正式投入使用与持续状态快照归档。
"""
        roadmap_path.write_text(roadmap_content, encoding="utf-8")

    dec_path = target_dir / "00_入口" / "02_决策记录.md"
    if not dec_path.exists():
        dec_content = f"""---
type: decision-log
status: active
updated: {today}
---

# 决策记录

本文件记录用户与主协调方明确拍板的工程级关键决策。

| ID | 日期 | 决策内容 | 状态 | 依据 |
|---|---|---|---|---|
| DEC-0001 | {today} | 建立标准十进制工程架构与 AGENTS.md 治理体系 | accepted | 工程初始化指令 |

## 规则
1. `accepted` 决策不得被 AI 静默改写。
2. 语义变更必须创建新 DEC 并标记 `supersedes`。
3. 被废弃的记录移入 `08_归档/superseded/`。
"""
        dec_path.write_text(dec_content, encoding="utf-8")

    risk_path = target_dir / "00_入口" / "03_开放问题与风险.md"
    if not risk_path.exists():
        risk_content = f"""---
type: open-issues-risk-register
status: active
updated: {today}
---

# 开放问题与风险登记册

| ID | 类别 | 问题 / 风险描述 | 状态 | 应对策略 / 阻塞项 |
|---|---|---|---|---|
| Q-001 | 需求 | 确认首个切片 (TS-001) 的最小 MVP 目标与验收标准 | open | 由协调方与人类共同审查冻结 |
"""
        risk_path.write_text(risk_content, encoding="utf-8")

    # 8. Create 07_运行记录/LOG.md
    log_path = target_dir / "07_运行记录" / "LOG.md"
    if not log_path.exists():
        log_content = f"""---
type: process-log
status: active
append_only: true
created: {today}
updated: {today}
---

# 过程运行流水账 (LOG)

本文件是全库唯一的纯追加过程事件流水账。严禁覆盖、删除或重排历史行；历史更正通过新追加的 `CORRECTION` 事件行表达。

| Event | Date | Type | Object | Change | Evidence | Next |
|---|---|---|---|---|---|---|
| PROC-0001 | {today} | BOOTSTRAP | project | 工程十进制目录架构、治理规范与 LLM-Wiki 知识层初始化完成 | `HANDOFF.md`, `AGENTS.md`, `{layer_05_name}/wiki` | 冻结需求与架构基线 |
"""
        log_path.write_text(log_content, encoding="utf-8")

    # 9. Create root HANDOFF.md
    handoff_path = target_dir / "HANDOFF.md"
    if not handoff_path.exists():
        handoff_content = f"""---
type: handoff
handoff_id: HO-BOOTSTRAP-001
status: canonical-initialized
sender: "{author}"
intended_receiver: "next-agent"
created: {today}
updated: {today}
state_pointer: "00_入口/00_当前.md"
workspace_path: "{target_dir.resolve()}"
---

# 当前全局交接：工程架构初始化完成

## 1. 项目背景与当前阶段
- **项目名称**: {project_name}
- **当前阶段**: P0 初始化基线已建立，工程骨架与治理合同就绪，等待第一个工作切片。
- **工作区绝对路径**: `{target_dir.resolve()}`
- **环境基线**: OS: {env['os']} | Python: {env['python']} | Git: {env['git']} | Node: {env['node']}

## 2. 已完成工作
1. 建立十进制分层工程目录结构（`00_入口` 到 `09_提案与草稿` + `templates/`）。
2. 建立全库治理准则 `AGENTS.md`，确立四方权力隔离、单事实源与六大状态词分离协议。
3. 建立全库唯一过程日志 `07_运行记录/LOG.md`，登记第一条 `PROC-0001 BOOTSTRAP` 事件。
4. 建立当前状态入口 `00_入口/00_当前.md` 与决策记录。
5. 核心不可变模板已归入 `templates/` 目录，JSON Schema 归入 `02_架构与合同/schemas/`。
6. 建立 OKF v0.2 LLM-Wiki 知识复利与工作记忆层（位于 `{layer_05_name}/wiki/`）。

## 3. 待完成工作与当前唯一下一步
- **唯一下一步**: 在 `01_需求与验收` 中明确系统需求与范围边界，由主协调方起草第一个 TaskSlice。

## 4. 核心设计边界与不变量 (Invariants)
- **单事实源**：唯一当前在 `00_入口/00_当前.md`，唯一过程流水在 `07_运行记录/LOG.md`，唯一当前交接在 `HANDOFF.md`。
- **沙箱隔离**：Worker 只能写自己的 attempt workspace，未经独立审核和人类批准，绝不直接写 canonical state。
- **状态分离**：测试通过 (tested) ≠ 人类验收 (human-accepted)。

## 5. 关键文件与状态对照表
| 文件路径 | 状态 | 依据与说明 |
|---|---|---|
| `AGENTS.md` | approved | 治理准则基线 |
| `HANDOFF.md` | canonical-initialized | 当前交接总线 |
| `00_入口/00_当前.md` | active | 唯一当前状态入口 |
| `07_运行记录/LOG.md` | active | 全库唯一过程流水账 |
| `{layer_05_name}/wiki/meta/index.md` | active | 知识库结构化总索引 |

## 6. 后续接手者操作指南
1. 严格按照 `AGENTS.md` 的会话启动顺序读取文件。
2. 任何过程操作必须在 `07_运行记录/LOG.md` 追加事件。
3. 任务闭环时务必使用 `wiki_tool.py retro` 提炼原子见解。

## 7. 知识复利与 LLM-Wiki 状态 (Compounding Knowledge)
- **项目知识库入口**: `{layer_05_name}/wiki/README.md`
- **结构化总索引**: `{layer_05_name}/wiki/meta/index.md`
- **任务复盘见解**: `{layer_05_name}/wiki/retro/`
- **工作记忆轨迹与技能**: `{layer_05_name}/wiki/trajectories/` 与 `{layer_05_name}/wiki/skills/`
- **个人知识库联动**: 跨工程经验自动联动个人知识库 `~/.llm-wiki`，使用 `wiki_tool.py recall` 进行分层召回。
"""
        handoff_path.write_text(handoff_content, encoding="utf-8")

    # 10. Populate index/readme in directories if missing
    index_files = [
        ("01_需求与验收/00_索引.md", "# 01_需求与验收 索引\n\n- 用户故事、范围、数据边界、Gate清单、错误处置与验收矩阵。\n"),
        ("02_架构与合同/00_索引.md", "# 02_架构与合同 索引\n\n- 实体与版本合同、TaskSlice与Handoff合同、可执行不变量与 JSON Schemas。\n"),
        ("04_测试与验收/00_索引.md", "# 04_测试与验收 索引\n\n- 契约测试、自动化测试策略、人类验收脚本与测试输入 fixtures。\n"),
        ("04_测试与验收/01_测试策略.md", "# 自动化分层测试策略\n\n1. 契约测试\n2. 单元测试\n3. 负向与边界测试\n4. 回滚与幂等测试\n"),
        (f"{layer_05_name}/00_索引.md", f"# {layer_05_name} 索引\n\n- raw, evidence, snapshots, claims, reports 资产导航。\n"),
        ("06_任务与交接/00_索引.md", "# 06_任务与交接 索引\n\n- active 在轨切片、completed 归档切片、records 凭据包、handoffs 历史交接。\n"),
        ("07_运行记录/README.md", "# 07_运行记录\n\n- 唯一过程流水账 LOG.md、历次执行 runs 与产物指针 artifacts。\n"),
        ("08_归档/README.md", "# 08_归档\n\n- superseded 废弃资产与 failed 失败记录。\n"),
        ("09_提案与草稿/README.md", "# 09_提案与草稿\n\n- Gate 批准前唯一的草稿隔离区，严禁直入 canonical。\n"),
    ]
    for rel_path, default_text in index_files:
        p = target_dir / rel_path
        if not p.exists():
            p.write_text(default_text, encoding="utf-8")

    print("[✔] Decuple Project initialized successfully!")


def main():
    parser = argparse.ArgumentParser(description="Initialize standardized project structure and handoff framework.")
    parser.add_argument("--target", "-t", type=str, default=".", help="Target project root directory (default: current dir)")
    parser.add_argument("--name", "-n", type=str, default="Engineering-Project", help="Project name")
    parser.add_argument("--author", "-a", type=str, default="Project-Init-Agent", help="Author/Agent identifier")
    parser.add_argument("--mode", "-m", choices=["decuple", "agile"], default="decuple", help="Initialization profile (decuple or agile)")
    parser.add_argument("--profile", "-p", choices=["r-icl", "research", "engineering"], default="r-icl", help="Decuple profile: r-icl (research, with 05_研究资产) or engineering (with 05_资产库)")
    parser.add_argument("--skip-contracts", action="store_true", help="Skip copying baseline contract files")
    parser.add_argument("--dry-run", action="store_true", help="Preview directory plan without creating files")

    args = parser.parse_args()
    target_dir = Path(args.target).resolve()

    # Locate resources relative to this script
    script_dir = Path(__file__).resolve().parent
    resources_dir = script_dir.parent / "resources"

    if args.mode == "decuple":
        init_decuple_project(
            target_dir=target_dir,
            project_name=args.name,
            author=args.author,
            resources_dir=resources_dir,
            profile=args.profile,
            skip_contracts=args.skip_contracts,
            dry_run=args.dry_run,
        )
    else:
        # Agile mode
        print(f"[*] Initializing Agile Project at {target_dir}")
        for d in AGILE_DIRS:
            (target_dir / d).mkdir(parents=True, exist_ok=True)
        # Agile minimal files
        today = datetime.date.today().isoformat()
        if not (target_dir / "AGENTS.md").exists():
            (target_dir / "AGENTS.md").write_text("# AGENTS.md (Agile Profile)\n\nSingle source of truth and state separation rules apply.\n", encoding="utf-8")
        if not (target_dir / "HANDOFF.md").exists():
            (target_dir / "HANDOFF.md").write_text(f"---\ntype: handoff\nstatus: active\ncreated: {today}\n---\n# Agile Handoff\n", encoding="utf-8")
        if not (target_dir / "07_运行记录" / "LOG.md").exists():
            (target_dir / "07_运行记录" / "LOG.md").write_text(f"---\ntype: process-log\nappend_only: true\ncreated: {today}\n---\n| Event | Date | Type | Object | Change | Evidence | Next |\n|---|---|---|---|---|---|---|\n| PROC-0001 | {today} | BOOTSTRAP | project | Agile initialized with .llm-wiki | HANDOFF.md | Start task |\n", encoding="utf-8")
        try:
            init_vault(target_dir / ".llm-wiki", is_personal=False)
        except Exception:
            pass
        print("[✔] Agile structure ready.")


if __name__ == "__main__":
    main()
