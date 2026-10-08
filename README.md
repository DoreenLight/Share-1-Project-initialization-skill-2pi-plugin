# Agent 资料归档 · 2026-10-06

本归档收录两份**仅存在于本机、未纳入 Git 版本管理**的资产:

| # | 内容 | 类型 | 原始位置 |
|---|------|------|---------|
| 01 | project-init-handoff | Agent Skill | `/Users/xbpd/.agents/skills/project-init-handoff` |
| 02 | pi-hub(`/hub` 插件) | pi Extension | `/Users/xbpd/.pi/agent/extensions` |

整理时间:2026-10-06 18:59 (Asia/Shanghai)

---

## 一、目录结构

```
Agent资料归档-20261006/
├── README.md                  ← 本文件,索引与还原说明
├── MANIFEST.md                ← 全量文件清单 + SHA-256 校验值
├── 01-技能-project-init-handoff/
│   └── project-init-handoff/  ← 技能目录,含 SKILL.md
└── 02-插件-pi-hub/
    └── extensions/            ← 保持相对路径,可整目录覆盖还原
        ├── hub.ts
        ├── lib/hub/{discover,server,state}.ts
        ├── lib/skills-deploy/{readme,paths}.ts
        └── __tests__/{hub.test.ts,hub-rpc.mjs}
```

---

## 二、01 · project-init-handoff(技能)

**作用**:标准化项目初始化、交接文档(worklog/LOG)管理、多智能体治理工作流。
内含 7 份契约、5 份 JSON Schema、17 份模板、4 个 Python 脚本与 2 个测试文件。

**还原方式**(覆盖回原位置):

```bash
cp -R "01-技能-project-init-handoff/project-init-handoff" \
      ~/.agents/skills/
```

已剔除运行期缓存:`__pycache__`、`.pytest_cache`、`*.pyc`、`.DS_Store`。

---

## 三、02 · pi-hub(插件)

**作用**:pi 的 `/hub` 斜杠命令,启动本地网页 Hub,在浏览器里手动开启/停用技能、扩展和包。
服务仅监听 `127.0.0.1`(默认端口 7864,端口号会浮动,实际地址见 `~/.pi/agent/hub-server.json`)。
开关写入 `~/.pi/agent/settings.json`,改完在 pi 里输入 `/reload` 或重启 pi 生效。

**为什么值得单独备份**:该插件目录**未被任何 Git 仓库跟踪**(`~/.pi/agent` 无 remote),
删掉就没有第二份副本。

**包含范围与依赖闭包**(已逐个文件核对 import):

| 文件 | 大小 | 说明 |
|------|------|------|
| `hub.ts` | 2.7 KB | 扩展入口,注册 `/hub` 命令 |
| `lib/hub/discover.ts` | 13 KB | 技能/扩展/包扫描 |
| `lib/hub/server.ts` | 51 KB | 本地 HTTP 服务与页面 |
| `lib/hub/state.ts` | 9.2 KB | 开关状态读写 |
| `lib/skills-deploy/readme.ts` | 14 KB | 被 `server.ts` 引用(渲染 README) |
| `lib/skills-deploy/paths.ts` | 1.5 KB | 被 `readme.ts` 引用 |
| `__tests__/hub.test.ts` | 18 KB | 测试 |
| `__tests__/hub-rpc.mjs` | 13 KB | RPC 测试夹具 |

**还原方式**:

```bash
cp -R "02-插件-pi-hub/extensions" ~/.pi/agent/
```

注意 `lib/skills-deploy/` 只收录了 hub 依赖的两个文件,不是该目录的完整副本;
其余 skills-deploy 代码若也需要备份请单独处理。

---

## 四、校验与说明

```bash
# 校验完整性(逐文件比对 SHA-256)
shasum -a 256 -c <(grep -E '^[0-9a-f]{64}  ' MANIFEST.md | sed 's|  |  ./|')
```

- U 盘为 **ExFAT**,不保存 POSIX 权限与扩展属性,macOS 访问时会自动生成 `._` 伴生文件。
  这些是文件系统产物,已在归档时清理,但重新访问后可能再次出现,属正常现象。
- 本归档**不含任何密钥或凭证**;pi-hub 的鉴权配置(`auth.json` 等)按安全惯例未纳入。
