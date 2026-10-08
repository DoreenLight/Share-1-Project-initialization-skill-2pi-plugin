/**
 * /hub — Skills 与插件管理 Hub：本地网页上手动开启/停用技能、扩展和包。
 *
 * 命令：
 *   /hub              启动 Hub 服务并打开浏览器
 *   /hub --no-open    只启动服务，不打开浏览器
 *
 * 开关写入 ~/.pi/agent/settings.json（与 pi config 同机制）。
 * 生效方式：在 pi 里输入 /reload（内建命令）或重启 pi。
 * 服务器仅监听 127.0.0.1。
 *
 * 注意：pi 的扩展 API 不暴露带命令路由的 prompt()，sendUserMessage 只会把
 * 文本发给 LLM（不会执行斜杠命令），所以 Hub 无法自己触发热重载 —— 页面上
 * 引导用户手动 /reload。
 */
import { spawn } from "node:child_process";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { resolveAgentDir, type HubTool } from "./lib/hub/discover.ts";
import { ensureHubServer, stopHubServer, type HubServerInfo } from "./lib/hub/server.ts";

export { resolveAgentDir };

function serialiseJson(value: unknown): unknown {
	try {
		return JSON.parse(JSON.stringify(value));
	} catch {
		return null;
	}
}

function currentTools(pi: ExtensionAPI): HubTool[] {
	try {
		const active = new Set(pi.getActiveTools());
		return pi
			.getAllTools()
			.map((tool) => ({
				id: `tool:${tool.name}`,
				name: tool.name,
				description: tool.description,
				parameters: serialiseJson(tool.parameters),
				promptGuidelines: [...(tool.promptGuidelines ?? [])],
				active: active.has(tool.name),
				sourceInfo: { ...tool.sourceInfo },
			}))
			.sort((a, b) => Number(b.active) - Number(a.active) || a.name.localeCompare(b.name));
	} catch {
		return [];
	}
}

export default function (pi: ExtensionAPI) {
	let starting: Promise<HubServerInfo> | null = null;

	function start(cwd: string): Promise<HubServerInfo> {
		if (!starting) {
			starting = ensureHubServer({ cwd, agentDir: resolveAgentDir(), getTools: () => currentTools(pi) }).catch((err) => {
				starting = null;
				throw err;
			});
		}
		return starting;
	}

	pi.on("session_start", async (_event, ctx) => {
		// One-shot print runs must not gain a listening socket.
		if (ctx.mode === "print") return;
		try {
			await start(ctx.cwd);
		} catch (err) {
			ctx.ui.notify(`Hub 服务启动失败：${err instanceof Error ? err.message : String(err)}`, "error");
		}
	});

	pi.on("session_shutdown", () => {
		stopHubServer();
	});

	pi.registerCommand("hub", {
		description: "打开 Skills/插件 Hub 网页（手动开启/停用技能、扩展和包）",
		handler: async (args, ctx) => {
			const info = await start(ctx.cwd);
			ctx.ui.notify(`Pi Hub: ${info.url}（改完在 pi 里 /reload 生效）`, "info");
			if (!/--no-open/.test(args) && ctx.mode === "tui" && process.platform === "darwin") {
				spawn("open", [info.url], { detached: true, stdio: "ignore" }).unref();
			}
		},
	});
}
