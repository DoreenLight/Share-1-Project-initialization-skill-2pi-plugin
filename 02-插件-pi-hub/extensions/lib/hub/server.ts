/**
 * hub server — local-only HTTP server serving the management page and a
 * small JSON API on top of discover/state helpers.
 *
 * Page design follows the /skills-deploy 展示台 system: three-pane layout
 * (partition sidebar + collapsible collections + markdown detail pane),
 * warm paper tones with teal accent, auto light/dark. markdownToHtml is
 * reused from lib/skills-deploy/readme.ts for previews.
 *
 * Singleton on globalThis so a `/reload` can close and re-bind with fresh
 * handlers (same pattern as lib/skills-deploy/server.ts).
 */
import { createServer, type IncomingMessage, type Server, type ServerResponse } from "node:http";
import { existsSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { collectSnapshot, type HubSnapshot, type HubTool } from "./discover.ts";
import { restoreParkedSkill, toggleLibrarySkill, togglePackage, toggleResource } from "./state.ts";
import { markdownToHtml } from "../skills-deploy/readme.ts";

export interface HubServerInfo {
	port: number;
	url: string;
}

export interface HubDeps {
	cwd: string;
	agentDir: string;
	/** Read the current session's registered and active tools on every refresh. */
	getTools?: () => HubTool[];
	/** Static tool snapshot for callers that do not have an ExtensionAPI. */
	tools?: HubTool[];
}

type Runtime = {
	server: Server | null;
	port: number;
	deps: HubDeps | null;
	startedAt: string;
};

const g = globalThis as typeof globalThis & { __PI_HUB_SERVER__?: Runtime };
const PREFERRED_PORTS = [7860, 7861, 7862, 7863, 7864];

function runtime(): Runtime {
	if (!g.__PI_HUB_SERVER__) {
		g.__PI_HUB_SERVER__ = { server: null, port: 0, deps: null, startedAt: "" };
	}
	return g.__PI_HUB_SERVER__;
}

function sendJson(res: ServerResponse, status: number, body: unknown) {
	res.writeHead(status, {
		"Content-Type": "application/json; charset=utf-8",
		"Cache-Control": "no-store",
	});
	res.end(JSON.stringify(body));
}

/**
 * Local-origin guard for /api/*. Blocks cross-site form/fetch CSRF against
 * 127.0.0.1 and DNS-rebinding (Host must be a loopback name). Browsers send
 * Sec-Fetch-Site/Origin on cross-site requests; curl and the RPC tests are
 * unaffected.
 */
function isLocalRequest(req: IncomingMessage): { ok: boolean; reason?: string } {
	const hostName = (req.headers.host ?? "").toLowerCase().replace(/:\d+$/, "").replace(/^\[|\]$/g, "");
	if (hostName !== "127.0.0.1" && hostName !== "localhost" && hostName !== "::1") {
		return { ok: false, reason: "rejected: non-loopback Host header" };
	}
	const site = req.headers["sec-fetch-site"];
	if (typeof site === "string" && site !== "same-origin" && site !== "none") {
		return { ok: false, reason: "rejected: cross-site request" };
	}
	const origin = req.headers.origin;
	if (typeof origin === "string" && origin !== "null") {
		try {
			const { hostname } = new URL(origin);
			if (hostname !== "127.0.0.1" && hostname !== "localhost" && hostname !== "[::1]" && hostname !== "::1") {
				return { ok: false, reason: "rejected: cross-origin request" };
			}
		} catch {
			return { ok: false, reason: "rejected: malformed Origin header" };
		}
	}
	return { ok: true };
}

function readBody(req: IncomingMessage, limit = 64 * 1024): Promise<string> {
	return new Promise((resolveBody, reject) => {
		const chunks: Buffer[] = [];
		let size = 0;
		req.on("data", (chunk: Buffer) => {
			size += chunk.length;
			if (size > limit) {
				reject(new Error("body too large"));
				req.destroy();
				return;
			}
			chunks.push(chunk);
		});
		req.on("end", () => resolveBody(Buffer.concat(chunks).toString("utf8")));
		req.on("error", reject);
	});
}

function toolSignature(tools: HubTool[]): string {
	return tools
		.map((tool) => `${tool.name}:${tool.active ? "on" : "off"}:${tool.sourceInfo.path}`)
		.sort()
		.join("\u0000");
}

function currentTools(deps: HubDeps): HubTool[] {
	try {
		return deps.getTools?.() ?? deps.tools ?? [];
	} catch {
		return deps.tools ?? [];
	}
}

function isHubAlive(port: number, agentDir: string, cwd: string, tools: HubTool[]): Promise<boolean> {
	return fetch(`http://127.0.0.1:${port}/api/ping`, { signal: AbortSignal.timeout(400) })
		.then(async (r) => {
			if (!r.ok) return false;
			const body = (await r.json()) as { hub?: boolean; agentDir?: string; cwd?: string; toolSignature?: string };
			return (
				body.hub === true &&
				body.agentDir === agentDir &&
				typeof body.cwd === "string" &&
				resolve(body.cwd) === resolve(cwd) &&
				body.toolSignature === toolSignature(tools)
			);
		})
		.catch(() => false);
}

function listen(server: Server, port: number, host = "127.0.0.1"): Promise<number> {
	return new Promise((resolvePort, reject) => {
		server.once("error", reject);
		server.listen(port, host, () => {
			const addr = server.address();
			if (addr && typeof addr === "object") resolvePort(addr.port);
			else reject(new Error("failed to bind hub server"));
		});
	});
}

async function freshState(deps: HubDeps): Promise<HubSnapshot & { port: number }> {
	const snapshot = await collectSnapshot(deps.cwd, deps.agentDir);
	return { ...snapshot, tools: currentTools(deps), port: runtime().port };
}

/**
 * Render a preview (markdown HTML) for a discovered resource, library skill,
 * or parked skill. Only paths that appear in a fresh snapshot are readable,
 * so the id acts as the authorization token — no traversal surface.
 */
async function handlePreview(deps: HubDeps, url: URL, res: ServerResponse) {
	const id = url.searchParams.get("id") ?? "";
	const snapshot = await collectSnapshot(deps.cwd, deps.agentDir);
	const resource = snapshot.resources.find((r) => r.id === id);
	const library = snapshot.library.find((s) => `lib:${s.path}` === id);
	const parked = snapshot.parked.find((p) => `parked:${p.path}` === id);

	let title = "";
	let path = "";
	let kind: "skill" | "source" = "skill";
	if (resource) {
		title = resource.name;
		path = resource.path;
		kind = resource.type === "skill" ? "skill" : "source";
	} else if (library || parked) {
		const item = library ?? parked;
		title = item.name;
		path = item.path;
	} else {
		sendJson(res, 404, { ok: false, error: "资源不存在，请刷新页面" });
		return;
	}

	let file = path;
	try {
		if (statSync(path).isDirectory()) file = join(path, "SKILL.md");
	} catch {
		sendJson(res, 500, { ok: false, error: "无法读取该资源" });
		return;
	}
	if (!existsSync(file)) {
		sendJson(res, 200, { ok: true, title, path, html: "<p class='md-empty'>没有可预览的 SKILL.md。</p>" });
		return;
	}
	const text = readFileSync(file, "utf8").slice(0, 128 * 1024);
	const html =
		kind === "skill" ? markdownToHtml(text) : markdownToHtml("```ts\n" + text.replace(/```/g, "``\u200b`") + "\n```");
	sendJson(res, 200, { ok: true, title, path, html });
}

function createRequestHandler(rt: Runtime) {
	return async (req: IncomingMessage, res: ServerResponse) => {
		const deps = rt.deps;
		if (!deps) {
			sendJson(res, 503, { ok: false, error: "hub server not initialized" });
			return;
		}
		const url = new URL(req.url || "/", `http://${req.headers.host || "127.0.0.1"}`);
		try {
			if (url.pathname.startsWith("/api/")) {
				const guard = isLocalRequest(req);
				if (!guard.ok) {
					sendJson(res, 403, { ok: false, error: guard.reason });
					return;
				}
				if (req.method === "POST") {
					const contentType = String(req.headers["content-type"] ?? "");
					if (!contentType.includes("application/json")) {
						sendJson(res, 415, { ok: false, error: "Content-Type must be application/json" });
						return;
					}
				}
			}
			if (url.pathname === "/api/ping") {
				const tools = currentTools(deps);
				sendJson(res, 200, {
					ok: true,
					hub: true,
					port: rt.port,
					agentDir: deps.agentDir,
					cwd: deps.cwd,
					toolSignature: toolSignature(tools),
				});
				return;
			}
			if (url.pathname === "/api/state") {
				sendJson(res, 200, { ok: true, state: await freshState(deps) });
				return;
			}
			if (url.pathname === "/api/preview") {
				await handlePreview(deps, url, res);
				return;
			}
			if (url.pathname === "/api/toggle" && req.method === "POST") {
				const body = JSON.parse((await readBody(req)) || "{}") as { id?: string; enabled?: boolean };
				const snapshot = await collectSnapshot(deps.cwd, deps.agentDir);
				const target = snapshot.resources.find((r) => r.id === body.id);
				if (!target) throw new Error("资源不存在，请刷新页面");
				await toggleResource(deps.cwd, deps.agentDir, target, body.enabled === true);
				sendJson(res, 200, { ok: true, state: await freshState(deps) });
				return;
			}
			if (url.pathname === "/api/package-toggle" && req.method === "POST") {
				const body = JSON.parse((await readBody(req)) || "{}") as {
					source?: string;
					enabled?: boolean;
					scope?: "user" | "project";
				};
				if (!body.source) throw new Error("缺少 source");
				if (body.scope !== undefined && body.scope !== "user" && body.scope !== "project") {
					throw new Error("非法的包作用域");
				}
				const snapshot = await collectSnapshot(deps.cwd, deps.agentDir);
				const candidates = snapshot.packages.filter((pkg) => pkg.source === body.source);
				const target = body.scope
					? candidates.find((pkg) => pkg.scope === body.scope)
					: candidates.length === 1
						? candidates[0]
						: undefined;
				if (!target) throw new Error("包不存在或作用域不明确，请刷新页面");
				if (target.scope !== "user") throw new Error("项目级包请在 pi config -l 中管理");
				if (!target.toggleable) throw new Error("带筛选规则的包不能整包切换，请逐项开关资源");
				await togglePackage(deps.cwd, deps.agentDir, target.source, body.enabled === true, target.scope);
				sendJson(res, 200, { ok: true, state: await freshState(deps) });
				return;
			}
			if (url.pathname === "/api/restore" && req.method === "POST") {
				const body = JSON.parse((await readBody(req)) || "{}") as { name?: string };
				if (!body.name) throw new Error("缺少 name");
				const to = restoreParkedSkill(deps.agentDir, body.name);
				sendJson(res, 200, { ok: true, restored: to, state: await freshState(deps) });
				return;
			}
			if (url.pathname === "/api/library-toggle" && req.method === "POST") {
				const body = JSON.parse((await readBody(req)) || "{}") as {
					path?: string;
					enabled?: boolean;
					scope?: "user" | "project";
				};
				if (!body.path) throw new Error("缺少 path");
				const snapshot = await collectSnapshot(deps.cwd, deps.agentDir);
				const target = snapshot.library.find((s) => s.path === body.path);
				if (!target) throw new Error("技能库中没有该项，请刷新页面");
				if (body.scope !== undefined && body.scope !== "user" && body.scope !== "project") {
					throw new Error("非法的技能库作用域");
				}
				if (target.scope === "project") throw new Error("项目级技能库挂载请在 pi config -l 中管理");
				if (body.scope === "project") throw new Error("技能库作用域与资源不匹配");
				await toggleLibrarySkill(deps.cwd, deps.agentDir, target.path, body.enabled === true, "user");
				sendJson(res, 200, { ok: true, state: await freshState(deps) });
				return;
			}
			if (url.pathname === "/" || url.pathname === "/index.html") {
				res.writeHead(200, { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-cache" });
				res.end(HUB_HTML);
				return;
			}
			sendJson(res, 404, { ok: false, error: "not found" });
		} catch (err) {
			sendJson(res, 500, { ok: false, error: err instanceof Error ? err.message : String(err) });
		}
	};
}

export async function ensureHubServer(deps: HubDeps): Promise<HubServerInfo> {
	const rt = runtime();
	rt.deps = deps;

	// An earlier runtime (pre-/reload) may still hold the port; its handlers
	// are stale, so always rebind with the current deps.
	if (rt.server) {
		try {
			rt.server.close();
		} catch {
			/* ignore */
		}
		rt.server = null;
		rt.port = 0;
	}

	// Reuse a hub instance already running in another pi session — but only
	// when it serves the same agentDir (e.g. tests or alternate PI_CODING_AGENT_DIR).
	const tools = currentTools(deps);
	for (const port of PREFERRED_PORTS) {
		if (await isHubAlive(port, deps.agentDir, deps.cwd, tools)) {
			rt.port = port;
			rt.startedAt = new Date().toISOString();
			return { port, url: `http://127.0.0.1:${port}/` };
		}
	}

	const server = createServer(createRequestHandler(rt));
	// Never let the socket keep a pi process alive on its own.
	server.unref();
	let port = 0;
	for (const candidate of PREFERRED_PORTS) {
		try {
			port = await listen(server, candidate);
			break;
		} catch {
			/* port busy, try next */
		}
	}
	if (!port) port = await listen(server, 0);

	rt.server = server;
	rt.port = port;
	rt.startedAt = new Date().toISOString();
	try {
		writeFileSync(
			join(deps.agentDir, "hub-server.json"),
			JSON.stringify({ url: `http://127.0.0.1:${port}/`, port, updatedAt: rt.startedAt }, null, 2) + "\n",
			"utf8",
		);
	} catch {
		/* best-effort */
	}
	return { port, url: `http://127.0.0.1:${port}/` };
}

export function stopHubServer(): void {
	const rt = runtime();
	if (rt.server) {
		try {
			rt.server.close();
		} catch {
			/* ignore */
		}
	}
	rt.server = null;
	rt.port = 0;
	rt.deps = null;
}

const HUB_HTML = `<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Pi Hub · 技能与插件管理</title>
<style>
  :root {
    color-scheme: light dark;
    --bg: #f3f0e8; --bg-elev: #fffdf8; --bg-sidebar: #ebe6db;
    --ink: #1c1917; --muted: #78716c; --line: rgba(28,25,23,.12);
    --accent: #0f766e; --accent-soft: rgba(15,118,110,.12);
    --warn: #b45309; --danger: #b91c1c;
    --shadow: 0 10px 30px rgba(28,25,23,.06);
    --sidebar-w: 240px; --detail-w: min(560px, 48vw);
    --mono: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    --sans: "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Noto Sans SC", sans-serif;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg: #0c0a09; --bg-elev: #1c1917; --bg-sidebar: #141110;
      --ink: #f5f5f4; --muted: #a8a29e; --line: rgba(245,245,244,.12);
      --accent: #2dd4bf; --accent-soft: rgba(45,212,191,.14); --warn: #fbbf24; --danger: #f87171;
      --shadow: 0 12px 32px rgba(0,0,0,.35);
    }
  }
  * { box-sizing: border-box; }
  html, body { height: 100%; }
  body { margin: 0; font-family: var(--sans); color: var(--ink); background: var(--bg); overflow: hidden; }
  .app { display: grid; grid-template-columns: var(--sidebar-w) 1fr; height: 100vh; }
  .app.detail-open { grid-template-columns: var(--sidebar-w) 1fr var(--detail-w); }
  .sidebar { background: var(--bg-sidebar); border-right: 1px solid var(--line); display: flex; flex-direction: column; min-height: 0; }
  .sidebar-head { padding: 1.1rem 1rem .6rem; }
  .sidebar-head h1 { margin: 0; font-size: 1.05rem; letter-spacing: -.02em; }
  .sidebar-head h1 .pi { color: var(--accent); }
  .sidebar-head p { margin: .35rem 0 0; color: var(--muted); font-size: .78rem; line-height: 1.45; }
  .nav { display: flex; flex-direction: column; gap: .25rem; padding: .4rem .65rem 1rem; overflow: auto; }
  .nav-item {
    appearance: none; border: 1px solid transparent; background: transparent;
    text-align: left; border-radius: 12px; padding: .65rem .7rem; cursor: pointer;
    color: var(--ink); font: inherit; display: grid; grid-template-columns: 1fr auto; gap: .15rem .5rem;
  }
  .nav-item:hover { background: color-mix(in srgb, var(--bg-elev) 70%, transparent); }
  .nav-item.active { background: var(--bg-elev); border-color: var(--line); box-shadow: var(--shadow); }
  .nav-label { font-weight: 650; font-size: .92rem; }
  .nav-count { font-variant-numeric: tabular-nums; font-size: .78rem; color: var(--accent); background: var(--accent-soft); border-radius: 999px; padding: .1rem .45rem; align-self: start; }
  .nav-sub { grid-column: 1 / -1; color: var(--muted); font-size: .72rem; }
  .sidebar-foot { margin-top: auto; padding: .75rem 1rem 1rem; color: var(--muted); font-size: .72rem; line-height: 1.5; border-top: 1px solid var(--line); }
  .sidebar-foot code { font-family: var(--mono); font-size: .68rem; }
  .main { display: flex; flex-direction: column; min-width: 0; min-height: 0; }
  .topbar {
    display: grid; grid-template-columns: 1fr auto; gap: .75rem; align-items: center;
    padding: .85rem 1.1rem; border-bottom: 1px solid var(--line);
    background: color-mix(in srgb, var(--bg) 88%, transparent); backdrop-filter: blur(10px);
    position: sticky; top: 0; z-index: 3;
  }
  .topbar input[type="search"] {
    width: 100%; border: 1px solid var(--line); background: var(--bg-elev); color: var(--ink);
    border-radius: 12px; padding: .7rem .85rem; font: inherit; box-shadow: var(--shadow);
  }
  .topbar input:focus { outline: 2px solid color-mix(in srgb, var(--accent) 55%, transparent); border-color: transparent; }
  .top-actions { display: flex; gap: .4rem; flex-wrap: wrap; }
  .btn {
    border: 1px solid var(--line); background: var(--bg-elev); color: var(--ink);
    border-radius: 10px; padding: .45rem .7rem; font: inherit; font-size: .82rem; cursor: pointer;
  }
  .btn:hover { border-color: color-mix(in srgb, var(--accent) 40%, var(--line)); }
  .btn.primary { background: var(--accent); color: #042f2e; border-color: transparent; font-weight: 650; }
  @media (prefers-color-scheme: light) { .btn.primary { color: #ecfdf5; } }
  .content { overflow: auto; padding: 1rem 1.1rem 3rem; }
  .hero { margin-bottom: 1rem; padding: 1rem 1.1rem; border: 1px solid var(--line); background: var(--bg-elev); border-radius: 16px; box-shadow: var(--shadow); }
  .hero h2 { margin: 0 0 .35rem; font-size: 1.1rem; }
  .hero p { margin: 0; color: var(--muted); line-height: 1.55; font-size: .88rem; max-width: 70ch; }
  .hero p code, .sidebar-foot code, .col-meta .path-inline { font-family: var(--mono); font-size: .8em; background: var(--accent-soft); padding: .08em .35em; border-radius: 6px; }
  .stats { display: flex; flex-wrap: wrap; gap: .45rem; margin-top: .75rem; }
  .pill { border: 1px solid var(--line); border-radius: 999px; padding: .25rem .65rem; font-size: .8rem; color: var(--muted); background: color-mix(in srgb, var(--bg) 50%, var(--bg-elev)); }
  .pill strong { color: var(--ink); }
  .pill.on strong { color: var(--accent); }
  .pill.off strong { color: var(--warn); }
  details.collection { border: 1px solid var(--line); background: var(--bg-elev); border-radius: 16px; margin-bottom: .85rem; box-shadow: var(--shadow); overflow: hidden; }
  details.collection.hidden { display: none; }
  details.collection > summary { list-style: none; cursor: pointer; padding: .95rem 1.05rem; display: grid; grid-template-columns: 1fr auto auto; gap: .25rem 1rem; align-items: start; user-select: none; }
  details.collection > summary::-webkit-details-marker { display: none; }
  details.collection > summary:hover { background: color-mix(in srgb, var(--accent-soft) 35%, transparent); }
  .col-title { margin: 0; font-size: 1.02rem; letter-spacing: -.02em; font-weight: 650; }
  .col-meta { color: var(--muted); font-size: .82rem; overflow-wrap: anywhere; grid-column: 1 / -1; }
  .chev { width: 1.6rem; height: 1.6rem; border-radius: 999px; border: 1px solid var(--line); display: grid; place-items: center; color: var(--muted); transition: transform .15s ease; font-size: .75rem; }
  details.collection[open] > summary .chev { transform: rotate(90deg); }
  .skills { display: grid; gap: .65rem; padding: 0 1rem 1rem; }
  .skill {
    border: 1px solid var(--line); border-radius: 14px; padding: .8rem .9rem;
    background: color-mix(in srgb, var(--bg) 55%, var(--bg-elev));
    transition: border-color .12s ease, box-shadow .12s ease;
  }
  .skill:hover { border-color: color-mix(in srgb, var(--accent) 45%, var(--line)); box-shadow: 0 0 0 3px var(--accent-soft); }
  .skill.hidden, .package-block.hidden { display: none; }
  .package-block {
    border: 1px solid var(--line); border-radius: 14px; padding: .8rem .9rem;
    background: color-mix(in srgb, var(--bg) 55%, var(--bg-elev));
    transition: border-color .12s ease, box-shadow .12s ease;
  }
  .package-block:hover { border-color: color-mix(in srgb, var(--accent) 45%, var(--line)); box-shadow: 0 0 0 3px var(--accent-soft); }
  .tool-source { margin: .55rem 0 0; color: var(--muted); font: .74rem/1.4 var(--mono); overflow-wrap: anywhere; }
  .tool-schema { margin-top: .6rem; border-top: 1px solid var(--line); padding-top: .5rem; }
  .tool-schema > summary { cursor: pointer; color: var(--accent); font-size: .8rem; font-weight: 650; }
  .tool-schema pre { margin: .5rem 0 0; max-height: 360px; overflow: auto; padding: .7rem .8rem; border: 1px solid var(--line); border-radius: 10px; background: color-mix(in srgb, var(--bg) 72%, #000); color: var(--ink); font: .75rem/1.45 var(--mono); white-space: pre-wrap; overflow-wrap: anywhere; }
  .tool-guidelines { margin: .55rem 0 0; padding-left: 1.2rem; color: var(--muted); font-size: .8rem; line-height: 1.45; }
  .skill-top { display: flex; flex-wrap: wrap; gap: .4rem .7rem; align-items: center; justify-content: space-between; margin-bottom: .3rem; }
  .skill-top h3 { margin: 0; font-size: .95rem; font-weight: 650; font-family: var(--mono); }
  .skill-top .left { display: flex; flex-wrap: wrap; gap: .45rem; align-items: center; min-width: 0; }
  .badge { font-size: .7rem; border-radius: 999px; padding: .12rem .45rem; border: 1px solid var(--line); color: var(--muted); white-space: nowrap; }
  .badge.core { color: var(--accent); border-color: color-mix(in srgb, var(--accent) 40%, var(--line)); background: var(--accent-soft); }
  .badge.off { color: var(--warn); border-color: color-mix(in srgb, var(--warn) 35%, var(--line)); }
  .badge.ro { color: var(--muted); background: color-mix(in srgb, var(--bg) 40%, var(--bg-elev)); }
  .skill-desc { margin: 0 0 .65rem; opacity: .9; line-height: 1.5; font-size: .88rem; }
  .path-row { display: grid; grid-template-columns: 1fr auto auto auto; gap: .4rem; align-items: stretch; }
  .path-box {
    font-family: var(--mono); font-size: .74rem; line-height: 1.4; padding: .5rem .6rem;
    border-radius: 10px; border: 1px dashed color-mix(in srgb, var(--accent) 35%, var(--line));
    background: color-mix(in srgb, var(--accent-soft) 55%, transparent); overflow-wrap: anywhere; user-select: all;
    align-self: center; color: var(--muted);
  }
  button.copy, button.preview-btn, button.restore-btn {
    border: 0; border-radius: 10px; padding: .5rem .7rem; font: inherit; font-size: .8rem; font-weight: 650; cursor: pointer; white-space: nowrap;
  }
  button.copy { background: var(--accent); color: #042f2e; }
  @media (prefers-color-scheme: light) { button.copy { color: #ecfdf5; } }
  button.copy.ok { background: #15803d; color: #ecfdf5; }
  button.copy.err { background: var(--warn); color: #1c1917; }
  button.preview-btn { background: color-mix(in srgb, var(--bg-elev) 80%, var(--accent-soft)); border: 1px solid var(--line); color: var(--ink); }
  button.restore-btn { background: color-mix(in srgb, var(--accent-soft) 70%, var(--bg-elev)); border: 1px solid var(--line); color: var(--accent); }
  .switch { position: relative; width: 42px; height: 23px; flex: none; }
  .switch input { opacity: 0; width: 100%; height: 100%; margin: 0; cursor: pointer; position: relative; z-index: 2; }
  .switch .track { position: absolute; inset: 0; background: color-mix(in srgb, var(--bg) 60%, var(--muted)); border: 1px solid var(--line); border-radius: 999px; transition: .15s; }
  .switch .knob { position: absolute; top: 3px; left: 3px; width: 15px; height: 15px; border-radius: 50%; background: var(--bg-elev); box-shadow: 0 1px 3px rgba(0,0,0,.25); transition: .15s; }
  .switch input:checked ~ .track { background: var(--accent); border-color: var(--accent); }
  .switch input:checked ~ .knob { left: 22px; }
  .switch input:disabled { cursor: not-allowed; }
  .switch input:disabled ~ .track { opacity: .55; }
  .switch-label { font-size: .74rem; color: var(--muted); font-weight: 650; white-space: nowrap; align-self: center; }
  .empty { display: none; text-align: center; color: var(--muted); padding: 2.2rem 1rem; border: 1px dashed var(--line); border-radius: 16px; }
  .empty.show { display: block; }
  .detail { display: none; border-left: 1px solid var(--line); background: var(--bg-elev); min-width: 0; min-height: 0; flex-direction: column; }
  .app.detail-open .detail { display: flex; }
  .detail-head { padding: .85rem 1rem; border-bottom: 1px solid var(--line); display: grid; gap: .45rem; }
  .detail-head h2 { margin: 0; font-size: 1rem; line-height: 1.35; font-family: var(--mono); }
  .detail-meta { color: var(--muted); font-size: .78rem; display: flex; flex-wrap: wrap; gap: .35rem .7rem; }
  .detail-actions { display: flex; flex-wrap: wrap; gap: .4rem; }
  .detail-body { overflow: auto; padding: 1rem 1.1rem 2.5rem; min-height: 0; }
  .detail-body .md-loading, .detail-body .md-empty { color: var(--muted); line-height: 1.55; }
  .md-body { line-height: 1.65; font-size: .92rem; }
  .md-body h1, .md-body h2, .md-body h3 { line-height: 1.3; letter-spacing: -.02em; margin: 1.25em 0 .5em; }
  .md-body h1 { font-size: 1.45rem; border-bottom: 1px solid var(--line); padding-bottom: .35rem; }
  .md-body h2 { font-size: 1.2rem; border-bottom: 1px solid var(--line); padding-bottom: .3rem; }
  .md-body h3 { font-size: 1.05rem; }
  .md-body p { margin: .7em 0; }
  .md-body a { color: var(--accent); }
  .md-body code { font-family: var(--mono); font-size: .85em; background: color-mix(in srgb, var(--accent-soft) 60%, transparent); padding: .1em .35em; border-radius: 6px; }
  .md-body pre.md-code { overflow: auto; padding: .85rem 1rem; border-radius: 12px; border: 1px solid var(--line); background: color-mix(in srgb, var(--bg) 70%, #000); font-size: .8rem; line-height: 1.45; }
  .md-body pre.md-code code { background: none; padding: 0; }
  .md-body table { border-collapse: collapse; width: 100%; font-size: .86rem; }
  .md-body th, .md-body td { border: 1px solid var(--line); padding: .45rem .55rem; vertical-align: top; }
  .md-body th { background: color-mix(in srgb, var(--accent-soft) 40%, transparent); text-align: left; }
  .md-body blockquote { margin: .8rem 0; padding: .2rem .9rem; border-left: 3px solid var(--accent); color: var(--muted); background: color-mix(in srgb, var(--accent-soft) 25%, transparent); }
  .md-body ul, .md-body ol { padding-left: 1.3rem; }
  .md-body hr { border: 0; border-top: 1px solid var(--line); margin: 1.2rem 0; }
  #toast {
    position: fixed; left: 50%; bottom: 28px; transform: translateX(-50%) translateY(20px);
    background: var(--bg-elev); border: 1px solid var(--accent); color: var(--ink); border-radius: 12px;
    padding: .6rem 1rem; font-size: .85rem; opacity: 0; transition: .25s; pointer-events: none; max-width: 80vw; box-shadow: var(--shadow); z-index: 40;
  }
  #toast.show { opacity: 1; transform: translateX(-50%) translateY(0); }
  #toast.err { border-color: var(--danger); }
  @media (max-width: 960px) {
    .app, .app.detail-open { grid-template-columns: 1fr; }
    .sidebar { position: fixed; inset: 0 auto 0 0; width: min(84vw, 280px); z-index: 20; transform: translateX(-105%); transition: transform .18s ease; box-shadow: var(--shadow); }
    .sidebar.open { transform: translateX(0); }
    .detail { position: fixed; inset: 0; z-index: 25; display: none; }
    .app.detail-open .detail { display: flex; }
    .path-row { grid-template-columns: 1fr; }
  }
  .mobile-nav-toggle { display: none; border: 1px solid var(--line); background: var(--bg-elev); border-radius: 10px; padding: .45rem .6rem; font: inherit; cursor: pointer; }
  @media (max-width: 960px) { .mobile-nav-toggle { display: inline-flex; } }
</style>
</head>
<body>
<div class="app" id="app">
  <aside class="sidebar" id="sidebar">
    <div class="sidebar-head">
      <h1><span class="pi">π</span> Pi Hub</h1>
      <p>pi 技能与插件管理 · 手动开启/停用，平时只保留最基础的资源</p>
    </div>
    <nav class="nav" id="nav"></nav>
    <div class="sidebar-foot">
      <div>配置目录 <code id="foot-agent">~/.pi/agent</code></div>
      <div style="margin-top:.35rem">改完在 pi 里输入 <code>/reload</code> 生效，或重启 pi。服务器仅监听 127.0.0.1。</div>
    </div>
  </aside>
  <main class="main">
    <div class="topbar">
      <input type="search" id="search" placeholder="搜索名称 / 描述 / 路径…" autocomplete="off" />
      <div class="top-actions">
        <button type="button" class="mobile-nav-toggle" id="nav-toggle">☰ 分区</button>
        <button type="button" class="btn" id="refresh">刷新</button>
        <button type="button" class="btn primary" id="reload-hint">如何生效？</button>
      </div>
    </div>
    <div class="content">
      <div class="hero">
        <h2>开关写入 settings.json，与 <code>pi config</code> 同机制</h2>
        <p>全局与当前项目的插件、技能、npm/git 包均在此展示；用户级资源可停用，项目级资源只读。技能库（<code>~/Projects/skills-hub</code>，由 <code>/skills-deploy --hub</code> 收纳）按需挂载；归档技能一键恢复。</p>
        <div class="stats" id="stats"></div>
      </div>
      <div id="collections"></div>
      <div class="empty" id="empty">没有匹配的资源</div>
    </div>
  </main>
  <aside class="detail" id="detail">
    <div class="detail-head">
      <h2 id="detail-title">—</h2>
      <div class="detail-meta" id="detail-meta"></div>
      <div class="detail-actions">
        <button type="button" class="btn" id="detail-close">关闭 (Esc)</button>
      </div>
    </div>
    <div class="detail-body" id="detail-body"><p class="md-loading">加载中…</p></div>
  </aside>
</div>
<div id="toast"></div>
<script>
var state = null;
var currentSection = "all";
var sections = [
  { id: "all", label: "全部", sub: "资源与包条目" },
  { id: "ext", label: "本地插件", sub: "全局 + 当前项目扩展" },
  { id: "skill", label: "技能", sub: "全局 + 当前项目 SKILL.md" },
  { id: "other", label: "其他资源", sub: "prompt / theme" },
  { id: "pkg", label: "npm / git 包", sub: "包与包内资源" },
  { id: "tool", label: "工具", sub: "当前 Pi 会话可用工具" },
  { id: "lib", label: "技能库", sub: "~/Projects/skills-hub 按需挂载" },
  { id: "parked", label: "已归档", sub: "skills-disabled 一键恢复" },
];

function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
    return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
  });
}

function toast(msg, isErr) {
  var el = document.getElementById("toast");
  el.textContent = msg;
  el.className = isErr ? "err show" : "show";
  setTimeout(function () { el.className = el.className.replace("show", "").trim(); }, 2600);
}

function api(path, body) {
  return fetch(path, body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : undefined)
    .then(function (r) { return r.json().then(function (data) { return { status: r.status, data: data }; }); });
}

function switchHtml(id, checked, disabled) {
  return '<label class="switch"><input type="checkbox" data-id="' + esc(id) + '"' +
    (checked ? " checked" : "") + (disabled ? " disabled" : "") +
    ' onchange="onToggle(this)" /><span class="track"></span><span class="knob"></span></label>';
}

function pathRow(path, previewId, extra) {
  return '<div class="path-row"><span class="path-box">' + esc(path) + "</span>" +
    '<button type="button" class="copy" data-copy="' + esc(path) + '">复制路径</button>' +
    (previewId ? '<button type="button" class="preview-btn" data-preview="' + esc(previewId) + '">预览</button>' : "") +
    (extra || "") + "</div>";
}

function cardHtml(r) {
  var badges = "";
  if (r.core) badges += '<span class="badge core">核心</span>';
  if (r.scope === "project") badges += '<span class="badge ro">项目级 · 只读</span>';
  if (r.scope === "temporary") badges += '<span class="badge ro">临时加载 · 只读</span>';
  if (!r.enabled && r.origin === "package") badges += '<span class="badge off">包已停用</span>';
  if (!r.enabled && r.origin === "top-level") badges += '<span class="badge off">已停用</span>';
  var disabled = r.scope !== "user";
  var checked = !!r.enabled;
  var switchLabel = disabled ? (checked ? "已开启 · 只读" : "已停用 · 只读") : (checked ? "已开启" : "已停用");
  var section = r.origin === "package" ? "pkg" : r.type === "extension" ? "ext" : r.type === "skill" ? "skill" : "other";
  return '<div class="skill" data-section="' + section + '" data-hay="' + esc((r.name + " " + (r.description || "") + " " + r.path).toLowerCase()) + '">' +
    '<div class="skill-top"><div class="left"><h3>' + esc(r.name) + "</h3>" + badges + '</div>' +
    '<span class="switch-label">' + switchLabel + "</span>" + switchHtml(r.id, checked, disabled) + "</div>" +
    (r.description ? '<p class="skill-desc">' + esc(r.description) + "</p>" : "") +
    pathRow(r.path, r.type === "skill" || r.type === "extension" ? r.id : "") +
    "</div>";
}

function libCardHtml(s) {
  var readOnly = s.scope === "project";
  var scopeBadge = readOnly ? '<span class="badge ro">项目级 · 只读</span>' : "";
  var mountBadge = s.enabled ? '<span class="badge core">已挂载</span>' : '<span class="badge ro">未挂载</span>';
  var switchLabel = readOnly ? "已挂载 · 只读" : (s.enabled ? "已挂载" : "未挂载");
  return '<div class="skill" data-section="lib" data-hay="' + esc((s.name + " " + (s.description || "") + " " + s.path).toLowerCase()) + '">' +
    '<div class="skill-top"><div class="left"><h3>' + esc(s.name) + "</h3>" + scopeBadge + mountBadge + '</div>' +
    '<span class="switch-label">' + switchLabel + "</span>" + switchHtml("lib:" + s.path, s.enabled, readOnly) + "</div>" +
    (s.description ? '<p class="skill-desc">' + esc(s.description) + "</p>" : "") +
    pathRow(s.path, "lib:" + s.path) + "</div>";
}

function parkedCardHtml(p) {
  return '<div class="skill" data-section="parked" data-hay="' + esc((p.name + " " + (p.description || "") + " " + p.path).toLowerCase()) + '">' +
    '<div class="skill-top"><div class="left"><h3>' + esc(p.name) + '</h3></div><span class="badge off">已归档</span></div>' +
    '<button type="button" class="restore-btn" data-restore="' + esc(p.name) + '">恢复到 skills/</button></div>' +
    (p.description ? '<p class="skill-desc">' + esc(p.description) + "</p>" : "") +
    pathRow(p.path, "parked:" + p.path) + "</div>";
}

function prettyJson(value) {
  try {
    return JSON.stringify(value, null, 2) || "{}";
  } catch (err) {
    return "[schema 无法序列化]";
  }
}

function toolCardHtml(t) {
  var sourceInfo = t.sourceInfo || {};
  var scope = sourceInfo.scope === "project" ? "项目级" : sourceInfo.scope === "temporary" ? "临时加载" : "用户级";
  var source = sourceInfo.path || sourceInfo.source || "Pi 内置";
  var badges = t.active
    ? '<span class="badge core">当前可用</span>'
    : '<span class="badge off">未启用</span>';
  badges += '<span class="badge ro">' + esc(scope) + "</span>";
  var guidelines = Array.isArray(t.promptGuidelines) ? t.promptGuidelines : [];
  return '<div class="skill tool-card" data-section="tool" data-hay="' +
    esc((t.name + " " + (t.description || "") + " " + source).toLowerCase()) + '">' +
    '<div class="skill-top"><div class="left"><h3>' + esc(t.name) + "</h3>" + badges + '</div>' +
    '<span class="switch-label">' + (t.active ? "当前可用" : "未启用") + "</span></div>" +
    (t.description ? '<p class="skill-desc">' + esc(t.description) + "</p>" : "") +
    (guidelines.length ? '<ul class="tool-guidelines">' + guidelines.map(function (line) { return "<li>" + esc(line) + "</li>"; }).join("") + "</ul>" : "") +
    '<p class="tool-source">来源：' + esc(source) + " · " + esc(scope) + '</p>' +
    '<details class="tool-schema"><summary>参数 schema（默认隐藏）</summary><pre>' + esc(prettyJson(t.parameters)) + "</pre></details>" +
    "</div>";
}

function collectionHtml(title, meta, section, inner, open) {
  return '<details class="collection" data-section="' + section + '"' + (open ? " open" : "") + ">" +
    '<summary><h2 class="col-title">' + esc(title) + "</h2>" +
    '<span class="chev">▶</span></summary>' +
    (meta ? '<div class="col-meta">' + meta + "</div>" : "") +
    '<div class="skills">' + inner + "</div></details>";
}

function pkgBlockHtml(pkg, children) {
  var childHtml = children.length
    ? children.map(cardHtml).join("")
    : '<div class="empty show">该包没有（匹配的）资源</div>';
  var readOnly = pkg.scope !== "user" || pkg.toggleable === false;
  var badges = pkg.scope === "project" ? '<span class="badge ro">项目级 · 只读</span>' : "";
  if (pkg.filtered && pkg.enabled) badges += '<span class="badge">含筛选规则 · 请逐项开关</span>';
  if (!pkg.enabled) badges += '<span class="badge off">已停用</span>';
  var switchLabel = pkg.scope === "project"
    ? "项目级 · 只读"
    : pkg.toggleable === false
      ? "请逐项开关"
      : (pkg.enabled ? "已开启" : "已停用");
  var head = '<div class="skill-top"><div class="left"><h3>' + esc(pkg.source) + "</h3>" + badges + '</div>' +
    '<span class="switch-label">' + switchLabel + "</span>" + switchHtml(pkg.id, pkg.enabled, readOnly) + "</div>";
  return '<div class="package-block" data-section="pkg" data-package="true" data-hay="' +
    esc((pkg.source + " " + pkg.scope).toLowerCase()) + '">' + head +
    '<div style="margin:.5rem 0 0 .7rem;display:grid;gap:.55rem">' + childHtml + "</div></div>";
}

function render() {
  if (!state) return;
  var q = (document.getElementById("search").value || "").trim().toLowerCase();
  var res = state.resources;
  var localExt = res.filter(function (r) { return r.type === "extension" && r.origin === "top-level"; });
  localExt.sort(function (a, b) { return (b.core ? 1 : 0) - (a.core ? 1 : 0) || a.name.localeCompare(b.name); });
  var localSkill = res.filter(function (r) { return r.type === "skill" && r.origin === "top-level"; });
  localSkill.sort(function (a, b) { return a.name.localeCompare(b.name); });
  var other = res.filter(function (r) {
    return r.origin === "top-level" && (r.type === "prompt" || r.type === "theme");
  });
  var pkgRes = res.filter(function (r) { return r.origin === "package"; });
  var lib = state.library || [];
  var parked = state.parked || [];
  var tools = state.tools || [];

  document.getElementById("foot-agent").textContent = state.agentDir;

  var on = res.filter(function (r) { return r.enabled; }).length + lib.filter(function (s) { return s.enabled; }).length;
  var off = res.length + lib.length - on;
  document.getElementById("stats").innerHTML =
    '<span class="pill on">已开启 <strong>' + on + "</strong></span>" +
    '<span class="pill off">已停用 <strong>' + off + "</strong></span>" +
    '<span class="pill">本地插件 <strong>' + localExt.length + "</strong></span>" +
    '<span class="pill">技能 <strong>' + localSkill.length + "</strong></span>" +
    '<span class="pill">包 <strong>' + state.packages.length + "</strong></span>" +
    '<span class="pill">工具 <strong>' + tools.length + "</strong></span>" +
    '<span class="pill">技能库 <strong>' + lib.length + "</strong></span>" +
    '<span class="pill">已归档 <strong>' + parked.length + "</strong></span>" +
    '<span class="pill">更新于 <strong>' + new Date(state.generatedAt).toLocaleTimeString() + "</strong></span>";

  var counts = {
    // Count visible entries, including one package container per configured package.
    all: res.length + lib.length + parked.length + state.packages.length + tools.length,
    ext: localExt.length, skill: localSkill.length, other: other.length,
    pkg: state.packages.length + pkgRes.length, tool: tools.length, lib: lib.length, parked: parked.length,
  };
  document.getElementById("nav").innerHTML = sections.map(function (s) {
    return '<button type="button" class="nav-item' + (currentSection === s.id ? " active" : "") + '" data-nav="' + s.id + '" title="' + esc(s.sub) + '">' +
      '<span class="nav-label">' + esc(s.label) + '</span><span class="nav-count">' + (counts[s.id] || 0) + "</span>" +
      '<span class="nav-sub">' + esc(s.sub) + "</span></button>";
  }).join("");

  var html = "";
  if (currentSection === "all" || currentSection === "ext") {
    html += collectionHtml("插件 · 本地扩展", "全局与当前项目扩展 · 停用后 /reload 生效", "ext",
      localExt.length ? localExt.map(cardHtml).join("") : '<div class="empty show">暂无</div>', currentSection === "ext" || currentSection === "all");
  }
  if (currentSection === "all" || currentSection === "skill") {
    html += collectionHtml("技能 · 全局与项目", "已发现的 SKILL.md · 项目级资源只读展示", "skill",
      localSkill.length ? localSkill.map(cardHtml).join("") : '<div class="empty show">暂无</div>', currentSection === "skill" || currentSection === "all");
  }
  if (currentSection === "all" || currentSection === "other") {
    if (other.length) {
      html += collectionHtml("其他资源 · prompt / theme", "模板类资源（项目级只读展示）", "other", other.map(cardHtml).join(""), currentSection === "other" || currentSection === "all");
    }
  }
  if (currentSection === "all" || currentSection === "pkg") {
    var pkgs = state.packages.slice().sort(function (a, b) { return a.source.localeCompare(b.source); });
    var pkgInner = pkgs.length
      ? pkgs.map(function (pkg) {
          var children = pkgRes.filter(function (r) { return r.source === pkg.source && r.scope === pkg.scope; });
          return pkgBlockHtml(pkg, children);
        }).join("")
      : '<div class="empty show">暂无已安装的包</div>';
    html += collectionHtml("包 · npm / git", "包内资源可单独开关；未过滤的用户包可整包开关 · /reload 后生效", "pkg", pkgInner, currentSection === "pkg" || currentSection === "all");
  }
  if (currentSection === "all" || currentSection === "tool") {
    html += collectionHtml("工具 · 当前 Pi 会话", "当前已注册工具 · 参数 schema 默认隐藏", "tool",
      tools.length ? tools.map(toolCardHtml).join("") : '<div class="empty show">当前会话没有已注册工具</div>', currentSection === "tool" || currentSection === "all");
  }
  if (currentSection === "all" || currentSection === "lib") {
    html += collectionHtml("技能库 · ~/Projects/skills-hub", "由 /skills-deploy --hub 收纳 · 用户级挂载后 /reload 生效", "lib",
      lib.length ? lib.map(libCardHtml).join("") :
      '<div class="empty show">技能库为空 —— 在 pi 里运行 /skills-deploy &lt;路径|git地址&gt; --hub 收纳技能</div>', currentSection === "lib" || currentSection === "all");
  }
  if (currentSection === "all" || currentSection === "parked") {
    if (parked.length) {
      html += collectionHtml("已归档技能 · skills-disabled/", "恢复 = 移回 skills/，/reload 后生效", "parked", parked.map(parkedCardHtml).join(""), currentSection === "parked" || currentSection === "all");
    }
  }

  var collectionsEl = document.getElementById("collections");
  collectionsEl.innerHTML = html;

  applyFilter(q);
}

function updateEmpty(q) {
  var collectionsEl = document.getElementById("collections");
  var visibleGroups = collectionsEl.querySelectorAll("details.collection:not(.hidden)");
  var hasVisibleResource = false;
  for (var g = 0; g < visibleGroups.length && !hasVisibleResource; g++) {
    var resources = visibleGroups[g].querySelectorAll(".skill:not(.hidden), .package-block:not(.hidden)");
    for (var i = 0; i < resources.length; i++) {
      if (!resources[i].closest(".hidden")) {
        hasVisibleResource = true;
        break;
      }
    }
  }
  var hasVisibleCollection = visibleGroups.length > 0;
  document.getElementById("empty").className = (!q && hasVisibleCollection) || (q && hasVisibleResource)
    ? "empty"
    : "empty show";
}

function applyFilter(q) {
  var groups = document.querySelectorAll("details.collection");
  for (var g = 0; g < groups.length; g++) {
    var group = groups[g];
    var sec = group.getAttribute("data-section");
    var selected = currentSection === "all" || sec === currentSection;
    var blocks = group.querySelectorAll(".package-block");
    for (var b = 0; b < blocks.length; b++) {
      var block = blocks[b];
      var blockHay = block.getAttribute("data-hay") || "";
      var blockMatch = !q || blockHay.indexOf(q) !== -1;
      var children = block.querySelectorAll(".skill");
      var childVisible = false;
      for (var c = 0; c < children.length; c++) {
        var childHay = children[c].getAttribute("data-hay") || "";
        var childMatch = !q || blockMatch || childHay.indexOf(q) !== -1;
        children[c].classList.toggle("hidden", !childMatch);
        if (childMatch) childVisible = true;
      }
      block.classList.toggle("hidden", !selected || (!!q && !blockMatch && !childVisible));
    }
    var cards = group.querySelectorAll(".skill");
    for (var i = 0; i < cards.length; i++) {
      if (cards[i].closest(".package-block")) continue;
      var hay = cards[i].getAttribute("data-hay") || "";
      cards[i].classList.toggle("hidden", !!q && hay.indexOf(q) === -1);
    }
    var visible = group.querySelector(".skill:not(.hidden), .package-block:not(.hidden)");
    var showGroup = selected && (!q || !!visible);
    group.classList.toggle("hidden", !showGroup);
    if (q && showGroup) group.open = true;
  }
  updateEmpty(q);
}

function refresh() {
  return api("/api/state").then(function (r) {
    if (r.status < 200 || r.status >= 300 || !r.data || !r.data.ok) {
      throw new Error((r.data && r.data.error) || "加载失败");
    }
    state = r.data.state;
    render();
  }).catch(function (err) {
    toast(err.message || "加载失败", true);
  });
}

function onToggle(input) {
  var id = input.getAttribute("data-id") || "";
  var enabled = input.checked;
  var target = null;
  var requestPath = "/api/toggle";
  var requestBody = { id: id, enabled: enabled };
  var messageKind = "resource";
  if (id.indexOf("pkg:") === 0) {
    if (state) {
      for (var p = 0; p < state.packages.length; p++) {
        if (state.packages[p].id === id) { target = state.packages[p]; break; }
      }
    }
    if (!target || target.scope !== "user" || target.toggleable === false) {
      input.checked = !enabled;
      toast("该包为项目级或含筛选规则，请逐项开关资源", true);
      return;
    }
    requestPath = "/api/package-toggle";
    requestBody = { source: target.source, scope: target.scope, enabled: enabled };
    messageKind = "package";
  } else if (id.indexOf("lib:") === 0) {
    var libPath = id.slice(4);
    var libTarget = null;
    if (state) {
      for (var l = 0; l < state.library.length; l++) {
        if (state.library[l].path === libPath) { libTarget = state.library[l]; break; }
      }
    }
    if (libTarget && libTarget.scope === "project") {
      input.checked = !enabled;
      toast("项目级技能库挂载请在 pi config -l 中管理", true);
      return;
    }
    requestPath = "/api/library-toggle";
    requestBody = { path: libPath, scope: "user", enabled: enabled };
    messageKind = "library";
  } else if (state) {
    for (var i = 0; i < state.resources.length; i++) {
      if (state.resources[i].id === id) { target = state.resources[i]; break; }
    }
  }
  if (target && target.core && !enabled) {
    if (!confirm("这是 Hub 自身。关闭后本页面将失效，需要编辑 settings.json 或用 pi config 重新开启。确定关闭？")) {
      input.checked = true;
      return;
    }
  }
  api(requestPath, requestBody).then(function (r) {
    if (r.status < 200 || r.status >= 300 || !r.data || !r.data.ok) {
      throw new Error((r.data && r.data.error) || "操作失败");
    }
    state = r.data.state;
    render();
    if (target && target.core && !enabled) toast("已关闭 Hub 自身，重启 pi 后生效");
    else if (messageKind === "library") toast(enabled ? "已挂载，/reload 或重启 pi 后生效" : "已卸载，/reload 或重启 pi 后生效");
    else if (messageKind === "package") toast(enabled ? "包已开启，/reload 或重启 pi 后生效" : "包已停用，/reload 或重启 pi 后生效");
    else toast(enabled ? "已开启，/reload 或重启 pi 后生效" : "已停用，/reload 或重启 pi 后生效");
  }).catch(function (err) {
    toast(err.message || "操作失败", true);
    refresh();
  });
}

function onRestore(name) {
  api("/api/restore", { name: name }).then(function (r) {
    if (r.status < 200 || r.status >= 300 || !r.data || !r.data.ok) {
      throw new Error((r.data && r.data.error) || "恢复失败");
    }
    state = r.data.state;
    render();
    toast("已恢复到 skills/，/reload 或重启 pi 后生效");
  }).catch(function (err) { toast(err.message || "恢复失败", true); });
}

function openPreview(id) {
  var app = document.getElementById("app");
  var body = document.getElementById("detail-body");
  document.getElementById("detail-title").textContent = "…";
  document.getElementById("detail-meta").textContent = "";
  body.innerHTML = '<p class="md-loading">加载中…</p>';
  app.className = "app detail-open";
  api("/api/preview?id=" + encodeURIComponent(id)).then(function (r) {
    if (r.status < 200 || r.status >= 300 || !r.data || !r.data.ok) {
      throw new Error((r.data && r.data.error) || "预览失败");
    }
    document.getElementById("detail-title").textContent = r.data.title;
    document.getElementById("detail-meta").textContent = r.data.path;
    body.innerHTML = '<div class="md-body">' + r.data.html + "</div>";
  }).catch(function (err) {
    body.innerHTML = '<p class="md-error">' + esc(err.message) + "</p>";
  });
}

function closePreview() {
  document.getElementById("app").className = "app";
}

document.addEventListener("click", function (ev) {
  var t = ev.target;
  if (!(t && t.closest)) return;
  var copy = t.closest("[data-copy]");
  if (copy) {
    var text = copy.getAttribute("data-copy");
    copy.textContent = "复制中…";
    navigator.clipboard.writeText(text).then(function () {
      copy.textContent = "已复制";
      copy.className = "copy ok";
      setTimeout(function () { copy.textContent = "复制路径"; copy.className = "copy"; }, 1200);
    }, function () {
      copy.textContent = "复制失败";
      copy.className = "copy err";
      setTimeout(function () { copy.textContent = "复制路径"; copy.className = "copy"; }, 1200);
    });
    return;
  }
  var preview = t.closest("[data-preview]");
  if (preview) { openPreview(preview.getAttribute("data-preview")); return; }
  var restore = t.closest("[data-restore]");
  if (restore) { onRestore(restore.getAttribute("data-restore")); return; }
  var nav = t.closest("[data-nav]");
  if (nav) {
    currentSection = nav.getAttribute("data-nav");
    document.getElementById("sidebar").className = "sidebar";
    render();
    return;
  }
});

document.getElementById("search").addEventListener("input", function () {
  applyFilter((this.value || "").trim().toLowerCase());
});
document.getElementById("nav-toggle").addEventListener("click", function () {
  var sb = document.getElementById("sidebar");
  sb.className = sb.className.indexOf("open") !== -1 ? "sidebar" : "sidebar open";
});
document.getElementById("refresh").onclick = refresh;
document.getElementById("reload-hint").onclick = function () {
  toast("已保存。在 pi 中输入 /reload 立即生效，或重启 pi 后生效");
};
document.getElementById("detail-close").onclick = closePreview;
document.addEventListener("keydown", function (ev) {
  if (ev.key === "Escape") closePreview();
});
window.addEventListener("focus", function () {
  api("/api/ping").then(function (r) {
    if (r.data && r.data.ok) refresh();
  }, function () {});
});

refresh();
</script>
</body>
</html>
`;
