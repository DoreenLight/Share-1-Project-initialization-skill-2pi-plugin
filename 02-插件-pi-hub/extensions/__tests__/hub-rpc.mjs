#!/usr/bin/env node
/**
 * RPC smoke for the /hub extension: command registration, HTTP API,
 * settings toggles, parked-skill restore, and cold-start effect of the
 * toggles — all against an isolated PI_CODING_AGENT_DIR, no LLM calls.
 * Run: node ~/.pi/agent/extensions/__tests__/hub-rpc.mjs
 */
import { spawn } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { connect as netConnect } from "node:net";

const root = mkdtempSync(join(tmpdir(), "hub-rpc-"));
const agentDir = join(root, "agent");
const workDir = join(root, "work");
const sessionDir = join(root, "sessions");
const libraryRoot = join(root, "skills-hub", "skills");
mkdirSync(join(agentDir, "skills", "alpha"), { recursive: true });
mkdirSync(join(agentDir, "skills-disabled", "beta"), { recursive: true });
mkdirSync(join(libraryRoot, "gamma"), { recursive: true });
mkdirSync(workDir, { recursive: true });
mkdirSync(sessionDir, { recursive: true });
writeFileSync(
	join(agentDir, "skills", "alpha", "SKILL.md"),
	"---\nname: alpha\ndescription: Alpha fixture skill for hub rpc smoke\n---\n# alpha\n",
);
writeFileSync(
	join(agentDir, "skills-disabled", "beta", "SKILL.md"),
	"---\nname: beta\ndescription: Beta parked fixture skill\n---\n# beta\n",
);
writeFileSync(
	join(libraryRoot, "gamma", "SKILL.md"),
	"---\nname: gamma\ndescription: Gamma library fixture skill\n---\n# gamma\n",
);

let stderrAll = "";

function fail(message) {
	console.error(message);
	if (stderrAll) console.error(stderrAll.slice(0, 4000));
	rmSync(root, { recursive: true, force: true });
	process.exit(1);
}

function wait(ms) {
	return new Promise((resolve) => setTimeout(resolve, ms));
}

async function startPi() {
	const proc = spawn(
		"pi",
		[
			"--mode",
			"rpc",
			"--no-extensions",
			"-e",
			"/Users/xbpd/.pi/agent/extensions/hub.ts",
			"--session-dir",
			sessionDir,
			"--no-session",
		],
		{ cwd: workDir, stdio: ["pipe", "pipe", "pipe"], env: { ...process.env, PI_CODING_AGENT_DIR: agentDir, PI_HUB_LIBRARY_DIR: libraryRoot } },
	);
	const state = { proc, buffer: "", events: [], pending: new Map(), nextId: 1 };
	proc.stdout.on("data", (chunk) => {
		state.buffer += chunk.toString("utf8");
		while (true) {
			const idx = state.buffer.indexOf("\n");
			if (idx === -1) break;
			const line = state.buffer.slice(0, idx).replace(/\r$/, "");
			state.buffer = state.buffer.slice(idx + 1);
			if (!line.trim()) continue;
			let msg;
			try {
				msg = JSON.parse(line);
			} catch {
				continue;
			}
			state.events.push(msg);
			if (msg.type === "response" && msg.id && state.pending.has(msg.id)) {
				state.pending.get(msg.id)(msg);
				state.pending.delete(msg.id);
			}
			if (msg.type === "extension_ui_request" && msg.method !== "notify") {
				proc.stdin.write(JSON.stringify({ type: "extension_ui_response", id: msg.id, cancelled: true }) + "\n");
			}
		}
	});
	proc.stderr.on("data", (chunk) => {
		stderrAll += chunk.toString("utf8");
	});
	state.send = (cmd) =>
		new Promise((resolve, reject) => {
			const id = `req-${state.nextId++}`;
			const timer = setTimeout(() => reject(new Error(`timeout waiting for ${id} ${cmd.type}`)), 20000);
			state.pending.set(id, (msg) => {
				clearTimeout(timer);
				resolve(msg);
			});
			proc.stdin.write(JSON.stringify({ id, ...cmd }) + "\n");
		});
	return state;
}

function stopPi(state) {
	return new Promise((resolve) => {
		const { proc } = state;
		proc.on("exit", resolve);
		try {
			proc.kill("SIGTERM");
		} catch {
			resolve();
		}
		setTimeout(resolve, 3000);
	});
}

async function commandNames(state) {
	const res = await state.send({ type: "get_commands" });
	if (!res.success) fail(`get_commands failed: ${JSON.stringify(res)}`);
	return res.data?.commands ?? [];
}

async function http(port, method, path, body) {
	const r = await fetch(`http://127.0.0.1:${port}${path}`, {
		method,
		headers: body ? { "Content-Type": "application/json" } : undefined,
		body: body ? JSON.stringify(body) : undefined,
	});
	return { status: r.status, data: await r.json().catch(() => ({})) };
}

async function httpRetry(port, method, path, body, timeoutMs = 10000) {
	const deadline = Date.now() + timeoutMs;
	let lastErr;
	while (Date.now() < deadline) {
		try {
			return await http(port, method, path, body);
		} catch (err) {
			lastErr = err;
			await wait(300);
		}
	}
	fail(`HTTP ${method} ${path} kept failing: ${lastErr}`);
}

/** Raw TCP request with a fully controlled Host / Sec-Fetch-Site header set. */
function rawRequest(port, headers, body = "") {
	return new Promise((resolve, reject) => {
		const socket = netConnect(port, "127.0.0.1", () => {
			socket.write(headers + "\r\n" + (body ? `Content-Length: ${Buffer.byteLength(body)}\r\n\r\n${body}` : "\r\n"));
		});
		let data = "";
		socket.on("data", (chunk) => (data += chunk.toString("utf8")));
		socket.on("error", reject);
		socket.on("close", () => resolve(data));
		setTimeout(() => {
			socket.destroy();
			resolve(data);
		}, 5000);
	});
}

try {
	// ── Phase 1: start hub, toggle alpha off, restore beta ──────────────
	const p1 = await startPi();
	let names = await commandNames(p1);
	if (!names.some((c) => c.name === "hub")) fail(`hub command missing: ${names.map((c) => c.name).join(",")}`);
	if (!names.some((c) => c.name === "skill:alpha")) fail(`skill:alpha missing: ${names.map((c) => c.name).join(",")}`);
	if (names.some((c) => c.name === "skill:beta")) fail("parked skill beta must not be discovered");

	const start = await p1.send({ type: "prompt", message: "/hub --no-open" });
	if (!start.success) fail(`/hub prompt failed: ${JSON.stringify(start)}`);
	await wait(500);
	const portMatch = p1.events.map((e) => JSON.stringify(e)).join("\n").match(/Pi Hub: http:\/\/127\.0\.0\.1:(\d+)/);
	if (!portMatch) fail(`hub URL notify not seen:\n${p1.events.slice(0, 20).map((e) => JSON.stringify(e)).join("\n")}`);
	const port = Number(portMatch[1]);

	const ping = await httpRetry(port, "GET", "/api/ping");
	if (ping.status !== 200 || ping.data.hub !== true) fail(`ping failed: ${JSON.stringify(ping)}`);

	const html = await (await fetch(`http://127.0.0.1:${port}/`)).text();
	if (!html.includes("Pi Hub") || !html.includes("已归档")) fail("hub page HTML missing expected content");
	if (!html.includes("skills-hub") || !html.includes("data-preview")) fail("hub page missing library/preview design features");

	const stateRes = await httpRetry(port, "GET", "/api/state");
	const tools = stateRes.data.state?.tools ?? [];
	const readTool = tools.find((tool) => tool.name === "read");
	if (!readTool || readTool.active !== true || typeof readTool.parameters !== "object") {
		fail(`read tool inventory missing or incomplete: ${JSON.stringify(readTool)}`);
	}
	const alpha = stateRes.data.state?.resources?.find((r) => r.name === "alpha");
	if (!alpha || alpha.enabled !== true) fail(`alpha not enabled in state: ${JSON.stringify(alpha)}`);
	if (!(stateRes.data.state?.parked ?? []).some((p) => p.name === "beta")) {
		fail(`beta not parked in state: ${JSON.stringify(stateRes.data.state?.parked)}`);
	}

	const preview = await httpRetry(port, "GET", `/api/preview?id=${encodeURIComponent(alpha.id)}`);
	if (preview.status !== 200 || !preview.data.ok) fail(`skill preview failed: ${JSON.stringify(preview)}`);
	if (!String(preview.data.html || "").includes("alpha")) fail("preview HTML missing skill content");
	if (preview.data.title !== "alpha") fail(`preview title wrong: ${preview.data.title}`);
	const badPreview = await http(port, "GET", "/api/preview?id=skill:/nowhere");
	if (badPreview.status !== 404) fail(`unknown preview id must 404, got ${badPreview.status}`);

	const off = await http(port, "POST", "/api/toggle", { id: alpha.id, enabled: false });
	if (off.status !== 200 || !off.data.ok) fail(`toggle off failed: ${JSON.stringify(off)}`);
	if (off.data.state.resources.find((r) => r.name === "alpha").enabled !== false) {
		fail("alpha still enabled after toggle off");
	}
	const settings = JSON.parse(readFileSync(join(agentDir, "settings.json"), "utf8"));
	if (!settings.skills?.includes("-skills/alpha/SKILL.md")) {
		fail(`settings missing disable pattern: ${JSON.stringify(settings.skills)}`);
	}

	const restore = await http(port, "POST", "/api/restore", { name: "beta" });
	if (restore.status !== 200 || !restore.data.ok) fail(`restore failed: ${JSON.stringify(restore)}`);
	if (!existsSync(join(agentDir, "skills", "beta", "SKILL.md"))) fail("beta not moved back into skills/");
	if (existsSync(join(agentDir, "skills-disabled", "beta"))) fail("beta still parked after restore");

	const bad = await http(port, "POST", "/api/toggle", { id: "skill:/nowhere", enabled: false });
	if (bad.status === 500 ? bad.data.ok !== false : true) fail(`unknown id should error: ${JSON.stringify(bad)}`);
	const evil = await http(port, "POST", "/api/restore", { name: "../evil" });
	if (evil.status === 500 ? evil.data.ok !== false : true) fail(`bad name should error: ${JSON.stringify(evil)}`);

	// CSRF / DNS-rebinding hardening: cross-site and non-loopback requests are rejected
	const forgedHost = await rawRequest(
		port,
		"GET /api/state HTTP/1.1\r\nHost: evil.example\r\nConnection: close",
	);
	if (!forgedHost.includes(" 403 ") || !forgedHost.includes("non-loopback Host")) {
		fail(`forged Host must be rejected: ${forgedHost.slice(0, 200)}`);
	}
	const crossSite = await rawRequest(
		port,
		`GET /api/state HTTP/1.1\r\nHost: 127.0.0.1:${port}\r\nSec-Fetch-Site: cross-site\r\nConnection: close`,
	);
	if (!crossSite.includes(" 403 ") || !crossSite.includes("cross-site")) {
		fail(`cross-site Sec-Fetch-Site must be rejected: ${crossSite.slice(0, 200)}`);
	}
	const crossOrigin = await rawRequest(
		port,
		`GET /api/state HTTP/1.1\r\nHost: 127.0.0.1:${port}\r\nOrigin: https://evil.example\r\nConnection: close`,
	);
	if (!crossOrigin.includes(" 403 ")) fail(`cross-origin Origin must be rejected: ${crossOrigin.slice(0, 200)}`);
	const textPlain = await fetch(`http://127.0.0.1:${port}/api/toggle`, {
		method: "POST",
		headers: { "Content-Type": "text/plain" },
		body: JSON.stringify({ id: alpha.id, enabled: true }),
	});
	if (textPlain.status !== 415) fail(`non-JSON POST must be 415, got ${textPlain.status}`);
	// the rejected request must not have toggled anything (alpha was disabled above)
	const stillOff = await http(port, "GET", "/api/state");
	if (stillOff.data.state.resources.find((r) => r.name === "alpha").enabled !== false) {
		fail("alpha must still be disabled after rejected CSRF attempts");
	}
	// normal same-origin requests keep working after rejections
	const pingAfter = await http(port, "GET", "/api/ping");
	if (pingAfter.data.ok !== true) fail("ping broken after CSRF rejections");

	// mount the skills-hub library skill via the API
	const libMount = await http(port, "POST", "/api/library-toggle", { path: join(libraryRoot, "gamma"), enabled: true });
	if (libMount.status !== 200 || !libMount.data.ok) fail(`library mount failed: ${JSON.stringify(libMount)}`);
	if (libMount.data.state.library.find((s) => s.name === "gamma").enabled !== true) {
		fail("gamma not marked enabled after mount");
	}
	const libSettings = JSON.parse(readFileSync(join(agentDir, "settings.json"), "utf8"));
	if (!libSettings.skills?.includes(join(libraryRoot, "gamma"))) {
		fail(`settings.skills missing library path: ${JSON.stringify(libSettings.skills)}`);
	}

	await stopPi(p1);

	// ── Phase 2: cold start honors toggles, restore, and library mount ──
	const p2 = await startPi();
	names = await commandNames(p2);
	if (names.some((c) => c.name === "skill:alpha")) fail(`skill:alpha must be gone after cold start: ${names.map((c) => c.name).join(",")}`);
	if (!names.some((c) => c.name === "skill:beta")) fail(`skill:beta must be discovered after restore: ${names.map((c) => c.name).join(",")}`);
	if (!names.some((c) => c.name === "skill:gamma")) fail(`skill:gamma must be discovered after library mount: ${names.map((c) => c.name).join(",")}`);
	if (!names.some((c) => c.name === "hub")) fail("hub command missing in phase 2");
	await stopPi(p2);

	// ── Phase 3: unmount in a fresh session, verify gone on next cold start ──
	const p3 = await startPi();
	const state3 = await commandNames(p3);
	if (!state3.some((c) => c.name === "skill:gamma")) fail("skill:gamma must be present at phase-3 start");
	const hubStart3 = await p3.send({ type: "prompt", message: "/hub --no-open" });
	if (!hubStart3.success) fail(`/hub prompt failed in phase 3: ${JSON.stringify(hubStart3)}`);
	await wait(500);
	const p3PortMatch = (() => {
		const text = p3.events.map((e) => JSON.stringify(e)).join("\n");
		const m = text.match(/Pi Hub: http:\/\/127\.0\.0\.1:(\d+)/);
		return m ? Number(m[1]) : 0;
	})();
	const unmount = p3PortMatch
		? await http(p3PortMatch, "POST", "/api/library-toggle", { path: join(libraryRoot, "gamma"), enabled: false })
		: { status: 0, data: { ok: false, error: "phase-3 hub server not found" } };
	if (unmount.status !== 200 || !unmount.data.ok) fail(`library unmount failed: ${JSON.stringify(unmount)}`);
	await stopPi(p3);

	const p4 = await startPi();
	names = await commandNames(p4);
	if (names.some((c) => c.name === "skill:gamma")) fail(`skill:gamma must be gone after unmount + cold start: ${names.map((c) => c.name).join(",")}`);
	await stopPi(p4);

	console.log("hub RPC smoke: ok");
	console.log(`port=${port} cold-start verified: alpha disabled, beta restored, gamma mount/unmount`);
	rmSync(root, { recursive: true, force: true });
	process.exit(0);
} catch (err) {
	fail(err instanceof Error ? err.stack ?? err.message : String(err));
}
