---
name: project-init-handoff
description: >-
  Standardized project initialization, handoff documentation, worklog/LOG management, and multi-agent
  governance workflow integrated with Karpathy's LLM-Wiki compounding knowledge engine (pi-llm-wiki) and
  Open Knowledge Format (OKF v0.2). Use when initializing projects, creating handoff files (HANDOFF.md),
  recording append-only logs (07_运行记录/LOG.md), managing task slices (TaskSlice, HandoffBundle, ResultBundle),
  running agent working-memory trajectories and skill distillations, maintaining layered wiki vaults
  (Personal ~/.llm-wiki/ + Project wiki/), or applying the robust 10-layer decuple directory architecture
  and governance canon derived from R-ICL.
---

# 工程初始化、交接管理与 LLM-Wiki 知识复利 Skill (project-init-handoff)

本 Skill 将科研级多 Agent 协作治理系统（源自 `R-ICL` 实验）的高抗逆、防篡改、强审计、单事实源与权力隔离体系，与 Andrej Karpathy 的 **LLM-Wiki 知识复利范式** 及 **Open Knowledge Format (OKF v0.2)** 深度融合。它为 Agent 在接手新工程、跨会话交接、过程流水审计、任务切片下发、沙箱受限实现、独立盲审验证、原子经验复盘 (`wiki_retro`)、求解工作记忆 (`trajectories`)、技能沉淀 (`skills`)、分层双库检索 (`layered_recall`) 与受控入库提供完整的工程标准与自动化工具箱。

---

## 1. 适用触发场景

1. **工程初始化与骨架搭建**：用户要求“初始化工程”、“建立项目骨架”、“规范化项目结构”、“按 R-ICL 架构初始化”、“初始化带 LLM-Wiki 的工程”；
2. **交接文档编制与跨会话恢复**：用户要求“准备交接”、“编写 handoff”、“更新交接文件”、“跨会话交接”；
3. **工作流水记录与审计**：用户要求“记录工作日志”、“维护 LOG.md”、“建立过程日志”、“追加运行记录”；
4. **任务切片派发与两阶段交付**：用户要求“拆解任务切片”、“下发 TaskSlice”、“准备 HandoffBundle / ResultBundle”、“实施独立盲审”、“候选成果入库”、“Promotion Plan 实施”；
5. **知识沉淀与原子复盘 (`wiki_retro`)**：用户要求“复盘本次任务”、“总结经验教训”、“沉淀原子知识点”、“避免下次踩坑”；
6. **Agent 工作记忆与轨迹沉淀 (`trajectories` & `skills`)**：用户要求“记录解决过程”、“记录工具调用轨迹”、“提炼可复用排障技能”、“提取 SOP Playbook”；
7. **分层知识检索 (`layered_recall`)**：用户要求“检索历史经验”、“我以前做过这个吗”、“查询知识库概念/实体”、“跨工程调取个人通用知识 (`~/.llm-wiki`)”；
8. **知识库机械式体检与元数据投影**：用户要求“检查 Wiki 健康度”、“排查断链与孤儿页面”、“重建 Wiki 索引与图谱 (`wiki_lint`, `rebuild_meta`)”。

---

## 2. 核心治理铁律 (Core Governance Invariants)

在工程中执行任何读写或状态跃迁前，必须严格遵守以下八大治理法则：

### 2.1 单事实源准则 (Single Source of Truth)
- **全库唯一物理当前状态**：`00_入口/00_当前.md`。全库在任何时刻只有一个权威当前状态，严禁在子目录维护并行的“当前状态”。
- **全库唯一过程流水账**：`07_运行记录/LOG.md`。纯追加 (append-only) 表格。严禁覆盖、删除或重排历史行；历史更正必须使用新追加的 `CORRECTION` 事件行表达。
- **全库唯一全局交接入口**：根目录 `HANDOFF.md`。专供人类与新 Agent 跨会话恢复上下文；历史交接归档于 `06_任务与交接/handoffs/`。
- **全库唯一知识总索引**：`05_研究资产/wiki/meta/index.md`（或 `05_资产库/wiki/meta/index.md`）。内容导向的确定性元数据投影，汇总概念、实体、综合、复盘、轨迹与技能。

### 2.2 四方权力边界隔离 (Quadrilateral Separation of Authority)
系统将参与主体划分为严格隔离的四方，杜绝利益冲突与越权：
- **用户 (Human Owner)**: 产品/科研目标、实质授权、人类验收和业务/科学边界的最终裁决者。
- **主协调 Agent (Coordinator)**: 负责拆解 TaskSlice、渲染派发交接包、独立复算 SHA-256、整合证据、暴露待决风险；**严禁自我批准**！
- **实现 Agent (Implementation Worker - IMPL)**: 严格按已冻结的任务包在白名单路径内实现；只能写自己的 attempt workspace，产出候选版本；**严禁直接写入 canonical 生产目录**。
- **审核 Agent (Validation Auditor - VAL)**: 独立责任视角，只读冻结合同与候选版本，在独立 workspace 执行盲审与交叉核对；只输出封闭工程判定，**严禁越权代替人类验收**。

### 2.3 六级状态词分离协议 (State Separation)
必须严格区分以下六级状态，绝对不可相互混淆或替代：
- `proposed`: 已提出，未经用户或相应 Gate 批准。
- `approved`: 用户或相应 Gate 已明确批准进入下一阶段。
- `implemented`: 候选代码或产物已生成，存在于 attempt workspace。
- `tested`: 自动化机器测试全部通过。
- `human-accepted`: 用户已完成真实交互、功能审查或场景使用验收。
- `scientifically-supported` (或 `verified-in-prod`): 结论或系统能力已获确凿证据链支撑。

> **警示**：工具返回成功 (exit code 0)、文件已生成或测试全部通过，**绝对不等于**人类验收通过或业务结论成立！

### 2.4 独立审核工程判定封闭词表 (VAL Verdicts)
审核 Worker 提交的 ResultBundle `verdict` 字段必须且仅限以下四词：
- `CONFORMANT`: 按冻结合同与候选 SHA 完成复算与测试，未发现工程偏差。
- `DEVIATIONS_FOUND`: 发现偏差、安全绕过或测试缺口，并附清单与复现依据。
- `INCOMPLETE`: 审核无法完成（如候选 SHA 漂移、环境缺失或输入不完整）。
- `OUT_OF_SCOPE`: 发现超出当前任务切片范围的事项，转主协调方或用户处置。

### 2.5 沙箱受限与两阶段入库规范 (Promotion Plan)
- **库根只读 + 白名单写入面 (Allowlist)**：Worker 只能写自己的 `03_实现/workspaces/<task_slice_id>/<attempt_id>/` 和受控 ResultBundle 提交通道。
- **两阶段交付 (Promotion Plan)**：
  1. **第一阶段（候选交付）**：Worker 将成果写入自身 workspace，提交包含产出物自报 SHA-256 的 `ResultBundle`。
  2. **第二阶段（晋升入库）**：协调方复算冻结候选 -> 独立审核方完成盲审与交叉核对并出具 `CONFORMANT` -> 人类完成真实使用验收并下发明确入库指令 -> 由主协调方原子执行 Canonical Bootstrap，逐文件比对 SHA 并晋升入库。

### 2.6 极小化交接通知协议 (Minimal Handoff Protocol)
跨会话或跨 Agent 的会话交互消息只传递五元组：
1. 文件物理绝对/相对路径 (`bundle_path`)；
2. 校验哈希 (`SHA-256`)；
3. 状态指针 (`state_pointer`)；
4. 发送方 (`sender`)；
5. 接收方 (`intended_receiver`)。
完整任务、上下文、执行结果与说明必须完全落入 `TaskSlice`、`HandoffBundle` 或 `ResultBundle` 物理文件中。

### 2.7 错误处置与 Fail-Closed 原则
- `fail_closed`: 提交前违规、自动 Gate 失败或 SHA 不符。零 canonical 写入，LOG 追加拒绝留痕。
- `needs_reconcile`: 提交后发现状态撕裂或不可信。阻断下游依赖，保持现场，人工介入。
- `stale/needs_review`: 上游版本变更导致的依赖陈旧。标记待审，不自动否定。
- `retry`: 无违规的可恢复环境故障。由人发起新 attempt，保留旧尝试历史。

### 2.8 知识持续复利与工作记忆守则 (Continuous Compounding & Working Memory)
- **会话易逝，知识长存 (Transience of Chat, Permanence of Wiki)**：对话历史与 Agent 记忆随会话结束而清理，但工程经验必须增量沉淀至 persistent wiki。
- **切片闭环必复盘 (`wiki_retro`)**：任何 TaskSlice 完成交付或发生重大阻断时，必须提炼至少一条原子工程见解（踩坑记录、隐蔽边界、反模式）沉淀至 `wiki/retro/`。
- **排障过程留轨迹 (`wiki_record_trajectory`)**：遇到复杂问题、多轮试错或技术攻坚时，记录工具调用链与突破点；批量提炼为 `wiki/skills/` 通用 Playbook。
- **个人知识库双向联动 (`~/.llm-wiki`)**：Agent 启动与探索时，通过 `layered_recall` 穿透检索项目与个人知识库，确保经验在多工程间自由复用。

---

## 3. LLM-Wiki 架构与 Open Knowledge Format (OKF v0.2) 标准

借鉴 Andrej Karpathy 的 LLM Wiki 架构与 `@zosmaai/pi-llm-wiki` 实践，本 Skill 建立了一套与 R-ICL 目录体系无缝耦合的知识中介层：

```text
[不可变输入层]       [持久化知识中介层 (Compounding Wiki)]          [确定性元数据投影]
+-------------+     +-----------------------------------+     +------------------+
| 原始来源    | --> | concepts/     (领域概念 CON-XXXX) | --> | meta/index.md    |
| (URL, 文件, |     | entities/     (系统组件 ENT-XXXX) |     | (分类总目录)      |
|  任务切片)  |     | synthesis/    (综合论证 SYN-XXXX) |     +------------------+
+-------------+     | retro/        (复盘见解 RETRO-XXX)| --> | meta/backlinks   |
                    | trajectories/ (工作记忆 TRAJ-XXXX)|     | (拓扑图谱)        |
                    | skills/       (标准技能 SKILL-XXX)|     +------------------+
                    | sources/      (不可变包 SRC-XXXX) | --> | meta/registry    |
                    +-----------------------------------+     +------------------+
```

### 3.1 OKF v0.2 规范化 Frontmatter 定义
所有 Wiki 页面必须遵从 Open Knowledge Format (OKF v0.2) 标准 YAML Frontmatter：
```yaml
---
id: CON-0001                          # 唯一实体标识 (CON, ENT, SYN, RETRO, TRAJ, SKILL, SRC)
title: "单事实源准则 (Single Source of Truth)" # 页面人类可读标题
type: concept                         # 页面类型: concept | entity | synthesis | retro | trajectory | skill | source
status: active                        # 状态: active | draft | immutable | recorded | distilled | archived
created: 2026-09-14                   # 创建日期 (YYYY-MM-DD)
updated: 2026-09-14                   # 更新日期 (YYYY-MM-DD)
aliases:                              # 别名列表，用于快速匹配与双向链接
  - "SSOT"
  - "单事实源"
tags:                                 # 分类标签
  - 核心架构
  - 治理法则
sources:                              # 关联的原始来源包或切片引用
  - "SRC-20260914-0001"
summary: "全库在任何时刻只有一个权威当前状态，严禁在子目录维护并行的当前状态。" # 一句话摘要（用于快速投影）
---
```

### 3.2 双向链接、标准 Markdown 链接与 Obsidian 兼容性
- **双轨链接支持 (Dual-Link Support)**：引擎同时支持标准 Obsidian Wikilinks（如 `[[concepts/CON-0001|单事实源]]`、`[[CON-0001]]`、带转义管道 `[[concepts/CON-0001\|别名]]`）与标准 Markdown 链接（如 `[单事实源](concepts/CON-0001.md)`、`[两阶段](./concepts/CON-0002.md)`）；
- **代码块与锚点安全解析**：自动过滤代码块（``` 与 `）内的示例代码链接，避免机械体检误报；支持锚点剥离与解析；
- **跨平台与跨工具互操作**：所有页面可在 Obsidian、Cursor、Claude Code、Windsurf 或普通 Markdown 查看器中直接可视化浏览、图形分析与点击穿梭；
- 支持稳定的来源引用标记 `[^SRC-XXXX]` 或 `[[sources/SRC-XXXX]]`。

### 3.3 双层知识库体系 (Layered Vault Architecture)
1. **项目知识库 (Project Vault)**：
   - 物理路径：`05_研究资产/wiki/`（科研/R-ICL profile）或 `05_资产库/wiki/`（工程 profile）或 `.llm-wiki/`（轻量工程）；
   - 范围：严格跟随 Git 仓库版本管理，记录该工程专属的概念、组件、切片复盘与业务综合。
2. **个人知识库 (Personal Vault)**：
   - 物理路径：`~/.llm-wiki/`；
   - 范围：跨越单个工程生命周期，承载开发者的通用排障技巧、通用 Python/TypeScript 性能分析法、环境踩坑记录与全球复用 Playbook；
   - 每次调用 `wiki_tool.py recall` 时，系统自动执行分层检索与去重，前置展示个人与项目结果（标注 `[📁 project]` 与 `[📓 personal]`）。

---

## 4. 17 项可执行不变量体系 (INV-001 ~ INV-017)

必须在代码、自动化脚本与门禁流程中强制检验：

| ID | 不变量描述 | 违反后果与处置 |
|---|---|---|
| **INV-001** | completed Run / immutable record / 捕获来源包 内容哈希永不改变 | 篡改触发 `needs_reconcile`，人工审查 |
| **INV-002** | `entity_id` 全局唯一，跨版本身份稳定（含 Wiki `CON-`, `RETRO-`, `SKILL-`） | 重复立即触发 `fail_closed` 拒绝 |
| **INV-003** | 每次 canonical mutation 必须对应一个 committed event | 事务不原子或无对应事件时触发 `fail_closed` |
| **INV-004** | 每个 Run 必须精确引用 ExperimentSpec / 方案版本与 SHA | 引用模糊或最新漂移时触发 `fail_closed` |
| **INV-005** | 每个 artifact / source reference 必须物理可解析且 SHA-256 匹配 | 哈希不匹配立即触发 `fail_closed` |
| **INV-006** | 每个 Claim 必须至少引用一个有效 EvidenceCard | 无证据主张触发 `fail_closed` 拒绝 |
| **INV-007** | workspace write 严禁越过 TaskSlice 白名单 (allowlist) | 越界写入触发 `fail_closed`，销毁 workspace |
| **INV-008** | derived index（Wiki `meta/index.md`、图谱、数据库缓存）可随时删除并确定性重建 | 丢失时清空重建，不视为数据损坏 |
| **INV-009** | definition revision 严禁原地改写历史已绑定的 Run | 修改必须创建新 revision 并标记 `supersedes` |
| **INV-010** | stale 状态只传播待审标记，绝不自动等同于科学或工程否定 | 仅标 `stale/needs_review`，等待人工裁决 |
| **INV-011** | Handoff / ResultBundle commit 必须具备幂等性 | 重复提交同一 bundle 返回已有记录，不生成重复事件 |
| **INV-012** | required integrity rule、Gate 配置缺失时默认 `fail_closed` | 门禁缺失直接拒绝执行，绝不默认放行 |
| **INV-013** | fixture/synthetic 纯合成证据严禁产生临床或生产真实有效性 Claim | **绝对禁止边界 (DENY)**，人工 Gate 亦无法解锁 |
| **INV-014** | EvidenceSnapshot 必须显式冻结 considered、included、excluded 证据集合 | 快照固定后只读不可变 |
| **INV-015** | 人类用户未验收前，严禁将对象状态标记为 `human-accepted` | 任何 Agent 自我宣布人类验收均视为严重违规 |
| **INV-016** | 只能引用已登记分类 (`data_class`)、版本与来源的数据文件 | 未登记数据触发 `fail_closed` |
| **INV-017** | 每次 `fail_closed` 必须追加完整拒绝记录，且严禁产生成功 Event 或 canonical mutation | 零 canonical 写入，仅在 `LOG.md` 留痕 |

---

## 5. 14 级治理门禁系统 (G-001 ~ G-014)

### 5.1 自动 Gate (Automatic Gates)
在任何 canonical transaction 提交前，底层必须自动检查：
`schema 格式` → `entity identity 与 version` → `reference 可解析性` → `TaskSlice allowlist` → `artifact hash` → `Wiki 机械检查 (broken links/frontmatter)` → `可执行不变量 (INV)` → `事务一致性`。
- 自动 Gate 拒绝时，全库零写入，返回原因；
- **人工批准绝对无法绕过自动 Gate**。

### 5.2 人工 Gate 清单 (Human Gates)
| Gate ID | 类别 | 触发动作 | 批准要求 | 结果边界 |
|---|---|---|---|---|
| **G-001** | 核心 Gate | 创建或语义修改定义与实体对象 | 必须人工批准 | 创建新 revision；不得原地覆盖历史 |
| **G-002** | 方案 Gate | 冻结或修订系统方案 / ExperimentSpec | 必须人工批准 | 冻结后不得改变已绑定 Run 的版本 |
| **G-003** | 任务 Gate | 批准任务切片 (TaskSlice) | 必须人工批准 | 批准计划、输入 SHA、范围、白名单、产物与停止条件 |
| **G-004** | 执行 Gate | 启动一次实际 Run / 尝试 | 每次均需 go/no-go | G-003 批准不等于本次 Run 自动启动 |
| **G-005** | 快照 Gate | 冻结 EvidenceSnapshot 证据集 | 必须人工批准 | 固定 included / considered / excluded 列表 |
| **G-006** | 证据 Gate | 接受或修订证据卡片 (EvidenceCard) | 必须人工批准 | 更正创建新版本，下游标 `stale` |
| **G-007** | 主张 Gate | 接受、撤回或标记 Claim | 必须人工批准 | 严禁 Agent 自我批准结论 |
| **G-008** | 升级 Gate | 将合成/测试集结果升级为方法论主张 | 必须人工批准 | 仅限方法/流程，保留 limitations（受 INV-013 约束） |
| **G-009** | 权限 Gate | 修改权限、allowlist、工具集或写入面 | 必须人工批准 | 先更新合同与负向测试，再改变运行策略 |
| **G-010** | 模板 Gate | 修改模板语义或 Schema 定义 | 必须人工批准 | 模板为合同入口，已有记录不被重写 |
| **G-011** | 阶段 Gate | 阶段跃迁 (如 P0→P1)、数据边界变更 | 必须人工批准 | 启动正式生产/实验均属新 Gate |
| **G-012** | 架构 Gate | 库级/目录级结构变更 | 必须人工批准 | 新增/重命名顶层目录、迁移子树均需 Gate |
| **G-013** | 处置 Gate | 异常处置、needs_reconcile 修复 | 必须人工批准 | 人工明确修复语义，不可静默恢复 |
| **G-014** | 迁移 Gate | canonical 文件迁移、删除或恢复 | 必须人工批准 | 核对 ID、版本、SHA、引用与回滚方案 |

---

## 6. 十进制分层工程架构蓝图 (Decuple File Architecture)

完整支持科研档案型 (`profile=r-icl`)、工程生产型 (`profile=engineering`) 与轻量敏捷型 (`mode=agile`)：

```text
<Project Root>/
├── AGENTS.md                   # 治理准则、四方权力边界与知识复利守则
├── README.md                   # 工程总索引、阅读启动顺序与架构概览
├── HANDOFF.md                  # 全库唯一当前全局交接总线
├── 00_入口/
│   ├── 00_当前.md              # 全库唯一当前状态入口
│   ├── 01_路线图.md            # 里程碑阶段 (P0, P1, P2...) 规划与前置依赖
│   ├── 02_决策记录.md          # 拍板生效的关键决策表 (DEC-XXXX)
│   └── 03_开放问题与风险.md    # 尚未收口的技术问题 (Q) 与风险登记 (R)
├── 01_需求与验收/
│   ├── 00_索引.md              # 需求层导航索引
│   ├── 01_MVP用户故事.md       # 端到端核心业务闭环故事
│   ├── 02_范围与非目标.md      # 明确“做什么”与“绝不做什么”
│   ├── 03_验收矩阵.md          # 验收维度、可测性指标与验收脚本索引
│   ├── 04_失败场景.md          # 显式登记的失败与拒绝场景 (F-XXXX)
│   ├── 05_Gate清单与批准边界.md# 分级 Gate 定义 (G-001 ~ G-014)
│   ├── 06_数据边界.md          # 数据分类封闭枚举 (fixture/synthetic/external)
│   ├── 07_错误处置与fail_closed.md # 四档处置语义与错误映射矩阵
│   └── 08_共享执行与审核合同.md # IMPL 与 VAL 共享的契约占位
├── 02_架构与合同/
│   ├── 00_索引.md              # 架构层导航索引
│   ├── 00_系统方案基线.md       # 系统总体设计与技术方案冻结版
│   ├── 01_实体与版本合同.md    # 核心实体规范、三层哈希规则与版本递增策略
│   ├── 02_TaskSlice与Handoff合同.md # 任务切片字段规范与生命周期状态机
│   ├── 04_可执行不变量.md      # 必须在代码与门禁中强制检查的不变量 (INV-001 ~ INV-017)
│   └── schemas/                # JSON Schema 验证基线
│       ├── task-slice.schema.json
│       ├── handoff-bundle.schema.json
│       ├── result-bundle.schema.json
│       ├── experiment-spec-readonly.schema.json
│       └── wiki-page.schema.json # OKF v0.2 Wiki 页面 Schema
├── 03_实现/
│   ├── core/                   # 核心正确性内核 (Correctness Kernel)
│   ├── plugins/                # 业务/科研能力插件目录
│   ├── adapters/               # 外部运行时/Worker 适配器
│   ├── cli/                    # 命令行与交互工具链
│   └── workspaces/             # 隔离沙箱工作区 (workspaces/<slice>/<attempt>/)
├── 04_测试与验收/
│   ├── 00_索引.md              # 测试层导航索引
│   ├── 01_测试策略.md          # 契约测试、单元测试、负向测试分层策略
│   ├── 02_人类验收脚本.md      # 人类交互真实演练与审查脚本
│   └── fixtures/               # 可重现的测试输入数据集与基准输出
├── 05_研究资产/ (工程型为 05_资产库/)
│   ├── 00_索引.md              # 资产导航索引
│   ├── raw/                    # 原始入库数据与只读证据
│   ├── evidence/               # 证据卡片 (EvidenceCard)
│   ├── snapshots/              # 状态与环境快照 (EvidenceSnapshot)
│   ├── claims/                 # 经证据支撑的工程/科研主张
│   ├── reports/                # 正式交付报告
│   └── wiki/                   # 原生集成 OKF v0.2 LLM-Wiki 知识库
│       ├── README.md           # Wiki 治理与使用说明
│       ├── concepts/           # 原子领域概念 (CON-XXXX)
│       ├── entities/           # 系统组件与接口实体 (ENT-XXXX)
│       ├── synthesis/          # 深度技术综述与方案对比 (SYN-XXXX)
│       ├── retro/              # 任务终结复盘与原子经验 (RETRO-XXXX)
│       ├── trajectories/       # Agent 工作记忆求解轨迹 (TRAJ-XXXX)
│       ├── skills/             # 提炼沉淀的通用操作与排障技能 (SKILL-XXXX)
│       ├── sources/            # 不可变外部来源捕获包 (SRC-XXXX)
│       └── meta/               # 确定性投影目录
│           ├── index.md        # 分类结构化总目录 (自动重建)
│           ├── observations.md # 会话实时观察与备忘
│           ├── backlinks.json  # 双向链接图谱
│           └── registry.json   # 实体元数据快速索引
├── 06_任务与交接/
│   ├── 00_索引.md              # 任务与交接导航索引
│   ├── active/                 # 当前在轨执行的 TaskSlice (已获 Gate 批准)
│   ├── completed/              # 已成功终结并归档的 TaskSlice
│   ├── records/                # 按 <slice>/<attempt>/ 留存的 Handoff/Result 不变凭据
│   └── handoffs/               # 历史全局 HANDOFF.md 归档与快照
├── 07_运行记录/
│   ├── README.md               # 运行记录说明
│   ├── LOG.md                  # 全库唯一纯追加过程事件流水账
│   ├── runs/                   # 历次自动化执行/实验的 RunManifest
│   └── artifacts/              # 运行产生的物理不可变制品指针
├── 08_归档/
│   ├── README.md               # 归档说明
│   ├── superseded/             # 被新版本废弃替代的历史资产
│   └── failed/                 # 执行失败或被否决的尝试留痕
├── 09_提案与草稿/              # Gate 批准前唯一的草稿隔离区 (严禁直入 canonical)
│   ├── README.md               # 草案区隔离要求说明
│   ├── task_slices/            # 待批准的 TaskSlice 草案
│   ├── experiment_specs/       # 待批准的方案草案
│   ├── definitions/            # 待批准的定义草案
│   ├── claims/                 # 待批准的主张草案
│   ├── evidence/               # 待批准的证据卡草案
│   └── mutation_requests/      # 状态变更申请草案
└── templates/                  # 19 份标准不可变模板库 (12 治理 + 7 Wiki)
    ├── TaskSlice.md            # 任务切片契约模板 (含 promotion_plan)
    ├── HandoffBundle.md        # 交接信封模板
    ├── ResultBundle.md         # 结果与证据凭据模板
    ├── TaskPackage.md          # 派发给开发 Worker 的静态任务包模板
    ├── ValidationReviewPackage.md # 派发给审核 Worker 的静态审核包模板
    ├── Claim.md                # 科学/工程结论主张模板
    ├── Decision.md             # 关键决策登记模板
    ├── EvidenceCard.md         # 证据卡片模板
    ├── EvidenceSnapshot.md     # 证据快照模板
    ├── ExperimentSpec.md       # 方案/实验规格模板
    ├── ResearchEvent.md        # 细粒度审计事件模板
    ├── RunManifest.md          # 执行与制品清单模板
    ├── WikiConcept.md          # OKF v0.2 概念定义模板
    ├── WikiEntity.md           # OKF v0.2 系统组件/实体模板
    ├── WikiSynthesis.md        # OKF v0.2 跨文档综合论证模板
    ├── WikiRetro.md            # OKF v0.2 任务复盘与原子见解模板
    ├── WikiTrajectory.md       # OKF v0.2 Agent 工作记忆求解轨迹模板
    ├── WikiSkillCase.md        # OKF v0.2 提炼可复用排障技能模板
    └── WikiSourcePacket.md     # OKF v0.2 不可变来源捕获包模板
```

---

## 7. 全流程标准作业程序 (SOP)

### SOP 1: 项目工程初始化 (Initialization)
1. 确认工程物理根路径；
2. 执行脚手架初始化命令：
   ```bash
   python3 ~/.agents/skills/project-init-handoff/scripts/init_project.py \
     --target /path/to/project --name "ProjectName" --mode decuple --profile r-icl
   ```
3. 脚手架自动建立十进制完整目录树、创建 `05_研究资产/wiki` 体系、复制 19 份对象模板、复制 5 份 JSON Schema、部署治理合同并在 `07_运行记录/LOG.md` 写入首条 `PROC-0001 BOOTSTRAP` 流水。

### SOP 2: 会话启动、上下文恢复与知识分层召回 (Session Startup & Layered Recall)
每次 Agent 启动或接手会话，**必须严格**按以下顺序执行：
1. 读取 `README.md`，获取项目架构定位；
2. 读取 `00_入口/00_当前.md`，确认全库唯一物理当前状态与唯一下一步；
3. 读取根目录 `HANDOFF.md`，获取上一任留下的全局交接上下文与风险；
4. 读取 `AGENTS.md`，重温权力边界与行为规范；
5. 读取 `06_任务与交接/active/`，定位当前正在执行的切片；
6. **执行分层知识召回**：针对当前切片目标或核心关键词，运行：
   ```bash
   python3 ~/.agents/skills/project-init-handoff/scripts/wiki_tool.py recall --query "<关键词>"
   ```
   联动检查项目库 (`05_研究资产/wiki/`) 与个人库 (`~/.llm-wiki`) 中是否已有现成解决方案或踩坑记录。

### SOP 3: 任务切片管理与派发 (Task Slicing & Dispatch)
1. **切片起草**：从 `templates/TaskSlice.md` 复制模板至 `09_提案与草稿/task_slices/`；
2. **必填字段与 Promotion Plan 检查**：必须包含 `task_slice_id`, `revision`, `objective`, `non_goals`, `exact_inputs`(含预期 SHA-256), `allowed_paths`(白名单), `promotion_plan`, `validation_commands`, `stop_conditions`；
3. **关联 Wiki 实体**：在 `exact_inputs` 或上下文描述中引用已有的 `[[concepts/...]]` 或 `[[skills/...]]`；
4. **Gate 批准**：经用户人工批准 (G-003) 后，将文件移入 `06_任务与交接/active/`；
5. **渲染交接包**：依据 `templates/TaskPackage.md` 渲染并生成 `06_任务与交接/records/<slice>/<attempt>/HO-XXXX.md`，使用 `verify_bundle.py --stamp` 注入自哈希。

### SOP 4: 沙箱受限实现与工作记忆记录 (Implementation & Trajectory Recording)
1. **沙箱限定**：IMPL Worker 只能在 `03_实现/workspaces/<task_slice_id>/<attempt_id>/` 内创建/修改文件；
2. **记录求解轨迹 (可选/攻坚时必填)**：当遇到复杂排障、环境兼容或方案突破时，使用 `wiki_tool.py record-trajectory` 记录工具调用序列、卡点与解法；
3. **完整正反测试**：编写并实测通过正向用例与负向边界用例；
4. **提交凭据包**：Worker 生成 `RB-XXXX.md`，记录执行命令、读取/写入路径、产物自报 SHA-256，并使用 `--stamp` 盖戳；
5. **协调方冻结**：主协调方独立复算候选文件物理 SHA-256，生成 `candidate-freeze.md`。

### SOP 5: 独立审核与盲审先行 (Validation Review)
1. **独立环境**：VAL Worker 采用独立会话，不得复用开发 Worker 的临时缓存；
2. **盲审先行 (Blind First)**：审核方直接拉取冻结合同与候选代码，独立执行测试命令，记录原始机器输出；
3. **交叉核对 (Cross-Check)**：比对开发 Worker 自报的 `ResultBundle`，排查有无伪造退出码或隐藏失败；
4. **出具封闭 Verdict**：审核方在审核 `ResultBundle` 中出具 `CONFORMANT`、`DEVIATIONS_FOUND`、`INCOMPLETE` 或 `OUT_OF_SCOPE`。

### SOP 6: 人类验收与晋升入库 (Promotion & Canonical Bootstrap)
1. **协调方汇总**：主协调方将开发凭据包与审核凭据包整合，向人类用户汇报客观实测证据；
2. **人类真实验收**：用户亲自审查或交互演练，确认符合预期；
3. **入库指令下发**：用户明确指示“批准候选入库”；
4. **Canonical Bootstrap 执行**：
   - 由协调方原子执行移动操作；
   - 逐文件比对候选文件 SHA-256 与冻结记录完全一致；
   - 将文件放置于 canonical 目录（如 `03_实现/core/`）；
   - 使用 `log_event.py` 在 `07_运行记录/LOG.md` 追加 `CANONICAL_BOOTSTRAP` 事件行；
   - 更新 `00_入口/00_当前.md` 与根目录 `HANDOFF.md`。

### SOP 7: 任务终结复盘与原子见解沉淀 (`wiki_retro`)
在任务完成、关闭切片并编写 `HANDOFF.md` 前，**必须执行原子复盘**：
1. 提取本切片实施中的核心技术洞察（踩坑点、隐蔽约束、第三方行为）；
2. 运行复盘沉淀命令：
   ```bash
   python3 ~/.agents/skills/project-init-handoff/scripts/wiki_tool.py retro \
     --title "关于 CAS 并发状态跃迁的重试语义" \
     --insight "直接覆写状态会引发并发撕裂。必须在写前核对 expected_version，失配则触发 fail_closed。" \
     --task-slice "TS001-IMPL" \
     --tags "concurrency,cas,governance"
   ```
3. 工具自动在 `05_研究资产/wiki/retro/` 生成 `RETRO-YYYYMMDD-XXXX.md`，并在 `07_运行记录/LOG.md` 追加 `WIKI_RETRO` 流水。

### SOP 8: 轨迹提炼通用技能 (`distill_skill`)
当多条求解轨迹 (`TRAJ-XXXX`) 指向同一类模式时，协调方执行技能萃取：
```bash
python3 ~/.agents/skills/project-init-handoff/scripts/wiki_tool.py distill-skill \
  --title "沙箱容器权限越界排查与修复标准流程" \
  --pattern "1. 检查 allowlist 配置; 2. 排查子进程继承路径; 3. 重定向临时产物至 workspace" \
  --trajectories "TRAJ-20260914-0001,TRAJ-20260914-0002" \
  --antipatterns "严禁使用通配符 '*' 或提升 root 权限绕过检查" \
  --checklist "检查路径白名单,复算SHA256,确认INV-007通过"
```
自动生成 `wiki/skills/SKILL-XXXX.md` 并将关联轨迹标记为 `distilled`。

### SOP 9: 知识库机械体检与确定性投影 (`lint` & `rebuild-meta`)
定期或在代码入库前，对 Wiki 知识库执行机械式健康体检：
```bash
# 1. 检查断链、孤儿页面、未索引页面与 Frontmatter 格式
python3 ~/.agents/skills/project-init-handoff/scripts/wiki_tool.py lint

# 2. 若存在未索引页面，使用 --fix 自动修复
python3 ~/.agents/skills/project-init-handoff/scripts/wiki_tool.py lint --fix

# 3. 强制根据底层页面全量重建 meta/index.md 与拓扑图谱 (满足 INV-008)
python3 ~/.agents/skills/project-init-handoff/scripts/wiki_tool.py rebuild-meta
```

### SOP 10: 跨会话全局交接更新与归档 (Handoff & Archival)
1. 会话结束前更新根目录 `HANDOFF.md`：
   - 更新当前阶段与已完成事项；
   - 更新当前唯一下一步；
   - 更新关键文件与状态对照表；
   - 更新 `第 7 节 知识复利与 LLM-Wiki 状态`（关联本次沉淀的 retro 与 skill）；
2. 若里程碑发生跨阶段跃迁，将前版交接文档按 `06_任务与交接/handoffs/HOFF-YYYYMMDD-序号.md` 归档；
3. 发送极小化交接通知（五元组）。

---

## 8. 配套工具箱完整手册 (Tooling Manual)

### 8.1 LLM-Wiki 知识复利与工作记忆引擎 (`scripts/wiki_tool.py`)

#### 初始化知识库
```bash
# 初始化当前项目的 Wiki (默认位于 05_研究资产/wiki 或 .llm-wiki)
python3 ~/.agents/skills/project-init-handoff/scripts/wiki_tool.py init

# 初始化个人跨工程通用知识库 (~/.llm-wiki)
python3 ~/.agents/skills/project-init-handoff/scripts/wiki_tool.py init --personal
```

#### 捕获不可变来源
```bash
# 捕获本地文件为不可变来源包（自动计算 SHA-256 并生成 SRC-XXXX）
python3 ~/.agents/skills/project-init-handoff/scripts/wiki_tool.py capture \
  --title "系统需求规格说明书 v1.0" \
  --file /path/to/spec.pdf \
  --tags "requirements,spec" \
  --summary "初代核心需求与验收指标。"

# 捕获外部 URL 来源
python3 ~/.agents/skills/project-init-handoff/scripts/wiki_tool.py capture \
  --title "Karpathy LLM-Wiki Gist" \
  --url "https://gist.github.com/karpathy/..." \
  --text "核心论点摘要..." \
  --tags "llm-wiki,paradigm"
```

#### 记录任务复盘原子见解
```bash
python3 ~/.agents/skills/project-init-handoff/scripts/wiki_tool.py retro \
  --title "避免使用静默默认参数进行哈希校验" \
  --insight "当参数缺省时，必须默认抛出异常 fail-closed，绝不能赋予默认放行策略。" \
  --task-slice "TS001-VAL" \
  --tags "security,fail-closed"
```

#### 会话实时观察备忘
```bash
python3 ~/.agents/skills/project-init-handoff/scripts/wiki_tool.py observe \
  --text "macOS Sonoma 环境下 node v20 子进程缓冲区存在 64KB 截断风险，改用临时文件缓冲。" \
  --author "IMPL-Worker" \
  --tags "macos,node,buffer"
```

#### 记录求解轨迹与提炼技能
```bash
# 1. 记录轨迹
python3 ~/.agents/skills/project-init-handoff/scripts/wiki_tool.py record-trajectory \
  --title "排查跨平台文件换行符导致的哈希不一致" \
  --objective "解决 Windows CRLF 与 Linux LF 规范化哈希冲突" \
  --steps "步骤1: 计算原始哈希; 步骤2: 发现 CRLF 导致自哈希不符; 步骤3: 增加规范化换行过滤" \
  --task-slice "TS002-IMPL" \
  --breakthrough "在计算前统一将 \r\n 归一化为 \n" \
  --tags "hash,cross-platform"

# 2. 提炼为复用技能
python3 ~/.agents/skills/project-init-handoff/scripts/wiki_tool.py distill-skill \
  --title "跨平台文本哈希规范化通用准则" \
  --pattern "在进行任何 SHA-256 前，先将所有 \\r\\n 替换为 \\n，并规范化 UTF-8 编码" \
  --trajectories "TRAJ-20260914-0001" \
  --checklist "检测换行符,统一UTF-8,验证哈希幂等"
```

#### 规范化解析与安全创建页面 (Ensure Page)
```bash
# 安全创建或解析已有概念页面（若已存在则幂等返回现有路径）
python3 ~/.agents/skills/project-init-handoff/scripts/wiki_tool.py ensure-page \
  --type concept \
  --title "确定性投影准则" \
  --summary "派生元数据与总目录可随时根据底层内容确定性重建。" \
  --tags "architecture,projection"

# 安全创建组件实体页面
python3 ~/.agents/skills/project-init-handoff/scripts/wiki_tool.py ensure-page \
  --type entity \
  --title "Wiki 审计流水记录器" \
  --aliases "WikiLogger,EventLog" \
  --tags "component,audit"
```

#### 来源批量摄取 (Ingest Sources)
```bash
# 批量处理 sources/ 目录中未摄取的来源包，自动生成结构化综述并建立双向追溯
python3 ~/.agents/skills/project-init-handoff/scripts/wiki_tool.py ingest

# 摄取指定来源包
python3 ~/.agents/skills/project-init-handoff/scripts/wiki_tool.py ingest --source SRC-20260914-0001
```

#### 快速元数据注册表搜索 (Search Registry)
```bash
# 快速基于生成的 registry.json 检索 ID、标题、别名与摘要
python3 ~/.agents/skills/project-init-handoff/scripts/wiki_tool.py search "单事实源"

# 输出 JSON 格式
python3 ~/.agents/skills/project-init-handoff/scripts/wiki_tool.py search "CAS" --json
```

#### 自动化维护计划 (Watch Crontab)
```bash
# 打印标准 crontab 定时维护行（每日自动执行 lint --fix 与 rebuild-meta）
python3 ~/.agents/skills/project-init-handoff/scripts/wiki_tool.py watch --schedule daily
```

#### 分层召回与技能检索 (Layered Recall & Recall Skill)
```bash
# 同时搜索项目库与个人库（支持多关键字分词加权匹配）
python3 ~/.agents/skills/project-init-handoff/scripts/wiki_tool.py recall "换行符 哈希"

# 按类型精确过滤 (concept, retro, skill, trajectory, source)
python3 ~/.agents/skills/project-init-handoff/scripts/wiki_tool.py recall --type skill "沙箱"

# 快捷召回提炼技能 (Recall Skill)
python3 ~/.agents/skills/project-init-handoff/scripts/wiki_tool.py recall-skill "沙箱权限"

# 仅搜索个人库 (~/.llm-wiki)
python3 ~/.agents/skills/project-init-handoff/scripts/wiki_tool.py recall --scope personal "profiling"

# 输出机器可读 JSON
python3 ~/.agents/skills/project-init-handoff/scripts/wiki_tool.py recall "CAS" --json
```

#### 机械体检与元数据投影
```bash
# 检查断链、孤儿页面、未索引页面与重复 ID/别名
python3 ~/.agents/skills/project-init-handoff/scripts/wiki_tool.py lint

# 自动修复未索引条目
python3 ~/.agents/skills/project-init-handoff/scripts/wiki_tool.py lint --fix

# 强制全量重建索引与图谱 (满足 INV-008)
python3 ~/.agents/skills/project-init-handoff/scripts/wiki_tool.py rebuild-meta

# 查看知识库运营看板
python3 ~/.agents/skills/project-init-handoff/scripts/wiki_tool.py status
```

#### 环境变量 WIKI_ROOT 支持
```bash
# 可通过环境变量显式固定知识库根路径（适用于 MCP 客户端如 Cursor、Windsurf、Claude Code）
export WIKI_ROOT="/path/to/my_project/05_研究资产/wiki"
python3 ~/.agents/skills/project-init-handoff/scripts/wiki_tool.py status
```

---

### 8.2 工程初始化脚本 (`scripts/init_project.py`)
```bash
# 1. 采用 R-ICL 科研档案型初始化（包含 05_研究资产/wiki 与全套治理合同）
python3 ~/.agents/skills/project-init-handoff/scripts/init_project.py \
  --target /path/to/my_project \
  --name "ProjectAlpha" \
  --author "Coordinator-Agent" \
  --mode decuple \
  --profile r-icl

# 2. 采用通用软件工程架构初始化（使用 05_资产库/wiki）
python3 ~/.agents/skills/project-init-handoff/scripts/init_project.py \
  --target /path/to/my_project \
  --name "SoftwareProject" \
  --profile engineering

# 3. 采用轻量敏捷架构初始化（包含 .llm-wiki/）
python3 ~/.agents/skills/project-init-handoff/scripts/init_project.py \
  --target /path/to/my_project \
  --mode agile
```

---

### 8.3 凭据包完整性验证与自哈希签发 (`scripts/verify_bundle.py`)
```bash
# 1. 验证交接包、结果包或 Wiki 页面的 Frontmatter、状态词与加密哈希
python3 ~/.agents/skills/project-init-handoff/scripts/verify_bundle.py \
  /path/to/records/TS001-IMPL/attempt-001/RB-0001.md

# 2. 附带沙箱写入白名单路径越界检查
python3 ~/.agents/skills/project-init-handoff/scripts/verify_bundle.py \
  /path/to/records/TS001-IMPL/attempt-001/RB-0001.md --check-allowlist

# 3. 一键计算并盖戳 bundle_sha256 (遵循规范化自哈希规则)
python3 ~/.agents/skills/project-init-handoff/scripts/verify_bundle.py \
  /path/to/records/TS001-IMPL/attempt-001/HO-0001.md --stamp
```

---

### 8.4 纯追加流水账记录器 (`scripts/log_event.py`)
```bash
# 追加过程决策审计事件
python3 ~/.agents/skills/project-init-handoff/scripts/log_event.py \
  --log /path/to/07_运行记录/LOG.md \
  --type DECISION \
  --object "Q-001" \
  --change "MVP 范围冻结并由用户批准" \
  --evidence "00_入口/00_当前.md" \
  --next "开始 TS-001 实施"

# 追加知识复盘审计事件
python3 ~/.agents/skills/project-init-handoff/scripts/log_event.py \
  --log /path/to/07_运行记录/LOG.md \
  --type WIKI_RETRO \
  --object "RETRO-20260914-0001" \
  --change "沉淀关于 CAS 并发锁的原子见解" \
  --evidence "05_研究资产/wiki/retro/RETRO-20260914-0001.md" \
  --next "更新系统架构合同"
```
