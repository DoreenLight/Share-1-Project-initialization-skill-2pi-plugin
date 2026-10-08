/**
 * hub state mutations — enable/disable resources by writing the same
 * `+path` / `-path` patterns and package object-form filters that
 * `pi config` writes, via SettingsManager.
 */
import { existsSync, mkdirSync, renameSync } from "node:fs";
import { join, relative } from "node:path";
import type { PackageSource } from "@earendil-works/pi-coding-agent";
import { loadPi, resolveSkillEntry } from "./discover.ts";
import type { HubResource, PackageScope, ResourceType } from "./discover.ts";

/**
 * Serialise settings read-modify-write cycles per agentDir. pi persists
 * settings with a plain writeFileSync, and each operation builds a fresh
 * SettingsManager, so concurrent toggles would otherwise race and lose
 * updates.
 */
const settingsLocks = new Map<string, Promise<unknown>>();

export function withSettingsLock<T>(agentDir: string, fn: () => Promise<T>): Promise<T> {
	const previous = settingsLocks.get(agentDir) ?? Promise.resolve();
	const next = previous.then(fn, fn);
	settingsLocks.set(agentDir, next.catch(() => undefined));
	return next;
}

export function stripMarker(entry: string): string {
	return entry.startsWith("!") || entry.startsWith("+") || entry.startsWith("-") ? entry.slice(1) : entry;
}

/**
 * Rewrite a settings path array so `pattern` ends up enabled/disabled.
 * Aliases (e.g. the absolute path alongside the relative pattern) are
 * collapsed so we never leave duplicate markers behind.
 */
export function updatePathArray(current: string[], pattern: string, enabled: boolean, aliases: string[] = []): string[] {
	const targets = new Set([pattern, ...aliases].map((p) => p.replaceAll("\\", "/")));
	const kept = current.filter((entry) => !targets.has(stripMarker(entry).replaceAll("\\", "/")));
	kept.push(enabled ? `+${pattern}` : `-${pattern}`);
	return kept;
}

function arrayKeyFor(type: ResourceType): "extensions" | "skills" | "prompts" | "themes" {
	return `${type}s` as const;
}

/**
 * The pattern pi matches for a resource: relative to its base directory
 * (agentDir for top-level, package root for package resources). Falls back
 * to the absolute path when the resource lives outside the base.
 */
export function patternFor(res: HubResource, agentDir: string): string {
	const base = res.baseDir ?? agentDir;
	const rel = relative(base, res.path);
	if (!rel || rel.startsWith("..")) return res.path;
	return rel.split("/").join("/");
}

export function sourceOf(entry: PackageSource): string {
	return typeof entry === "string" ? entry : entry.source;
}

export function disablePackageEntry(entry: PackageSource): PackageSource {
	if (typeof entry !== "string") {
		throw new Error("带筛选规则的包不能整包切换，请逐项开关资源");
	}
	return { source: entry, extensions: [], skills: [], prompts: [], themes: [] };
}

export function enablePackageEntry(entry: PackageSource): PackageSource {
	return sourceOf(entry);
}

function applyTopLevelPaths(
	settings: SettingsManager,
	type: ResourceType,
	paths: string[],
): void {
	switch (type) {
		case "extension":
			settings.setExtensionPaths(paths);
			break;
		case "skill":
			settings.setSkillPaths(paths);
			break;
		case "prompt":
			settings.setPromptTemplatePaths(paths);
			break;
		case "theme":
			settings.setThemePaths(paths);
			break;
	}
}

/** Toggle a single discovered resource (global/user scope only). */
export async function toggleResource(
	cwd: string,
	agentDir: string,
	res: HubResource,
	enabled: boolean,
): Promise<void> {
	return withSettingsLock(agentDir, () => toggleResourceLocked(cwd, agentDir, res, enabled));
}

async function toggleResourceLocked(
	cwd: string,
	agentDir: string,
	res: HubResource,
	enabled: boolean,
): Promise<void> {
	if (res.scope !== "user") {
		throw new Error("项目级资源请在 pi config -l 中管理");
	}
	const { SettingsManager } = await loadPi();
	const settings = SettingsManager.create(cwd, agentDir);
	const key = arrayKeyFor(res.type);
	const pattern = patternFor(res, agentDir);

	if (res.origin === "top-level") {
		const current = (settings.getGlobalSettings()[key] as string[] | undefined) ?? [];
		applyTopLevelPaths(settings, res.type, updatePathArray(current, pattern, enabled, [res.path]));
	} else {
		const source = res.source;
		if (!source) throw new Error("资源缺少包来源信息");
		const packages = [...(settings.getGlobalSettings().packages ?? [])];
		const index = packages.findIndex((entry) => sourceOf(entry) === source);
		if (index === -1) throw new Error(`settings.json 中找不到包 ${source}`);
		let pkg = packages[index];
		if (typeof pkg === "string") {
			pkg = { source: pkg };
			packages[index] = pkg;
		}
		const packageObject = pkg as Record<string, unknown>;
		const packageArrays = ["extensions", "skills", "prompts", "themes"].map((name) =>
			Array.isArray(packageObject[name]) ? (packageObject[name] as unknown[]) : undefined,
		);
		const fullyDisabled = packageArrays.every((values) => values !== undefined && values.length === 0);
		if (!enabled && fullyDisabled) return;
		const key = arrayKeyFor(res.type);
		if (enabled && fullyDisabled) {
			// A package disabled with empty filters has no autoload baseline. Use a
			// normal filter that keeps every sibling visible-but-off, then force
			// include this child; otherwise Pi's delta mode would hide the siblings.
			delete packageObject.autoload;
			packageObject[key] = updatePathArray(["!**"], pattern, true, [res.path]);
		} else {
			const current = (packageObject[key] as string[] | undefined) ?? [];
			packageObject[key] = updatePathArray(current, pattern, enabled, [res.path]);
		}
		settings.setPackages(packages);
	}
	await settings.flush();
}

/** Toggle an unfiltered user package: empty-array filters disable, string form enables. */
export async function togglePackage(
	cwd: string,
	agentDir: string,
	source: string,
	enabled: boolean,
	scope: PackageScope = "user",
): Promise<void> {
	return withSettingsLock(agentDir, () => togglePackageLocked(cwd, agentDir, source, enabled, scope));
}

async function togglePackageLocked(
	cwd: string,
	agentDir: string,
	source: string,
	enabled: boolean,
	scope: PackageScope,
): Promise<void> {
	if (scope !== "user") throw new Error("项目级包请在 pi config -l 中管理");
	const { SettingsManager } = await loadPi();
	const settings = SettingsManager.create(cwd, agentDir);
	const packages = [...(settings.getGlobalSettings().packages ?? [])];
	const index = packages.findIndex((entry) => sourceOf(entry) === source);
	if (index === -1) throw new Error(`settings.json 中找不到包 ${source}`);
	const entry = packages[index];
	if (typeof entry !== "string") {
		const arrays = ["extensions", "skills", "prompts", "themes"].map((key) =>
			Array.isArray((entry as Record<string, unknown>)[key])
				? ((entry as Record<string, unknown>)[key] as unknown[])
				: undefined,
		);
		const fullyDisabled =
			arrays.every((values) => values !== undefined && values.length === 0) &&
			(entry as Record<string, unknown>).autoload !== false;
		if (!enabled || !fullyDisabled) {
			throw new Error("带筛选规则的包不能整包切换，请逐项开关资源");
		}
	}
	packages[index] = enabled ? enablePackageEntry(entry) : disablePackageEntry(entry);
	settings.setPackages(packages);
	await settings.flush();
}

/** Move a parked skill from `<agentDir>/skills-disabled/` back into `skills/`. */
export function restoreParkedSkill(agentDir: string, name: string): string {
	if (!/^[\w][\w.-]*$/.test(name)) throw new Error("非法的技能名称");
	const parkedRoot = join(agentDir, "skills-disabled");
	const candidates = [
		{ from: join(parkedRoot, name), to: join(agentDir, "skills", name) },
		{ from: join(parkedRoot, `${name}.md`), to: join(agentDir, "skills", `${name}.md`) },
	];
	const candidate = candidates.find(({ from }) => existsSync(from));
	if (!candidate) throw new Error(`归档目录中不存在 ${name}`);
	if (existsSync(candidate.to)) throw new Error(`skills/ 中已存在同名技能 ${name}`);
	mkdirSync(join(agentDir, "skills"), { recursive: true });
	renameSync(candidate.from, candidate.to);
	return candidate.to;
}

/**
 * Mount/unmount a skills-hub library skill by adding/removing its absolute
 * path in the settings `skills` array (pi's extra-location mechanism).
 * Only entries resolving exactly to `path` are touched.
 */
export async function toggleLibrarySkill(
	cwd: string,
	agentDir: string,
	path: string,
	enabled: boolean,
	scope: PackageScope = "user",
): Promise<void> {
	if (scope !== "user") throw new Error("项目级技能库挂载请在 pi config -l 中管理");
	return withSettingsLock(agentDir, async () => {
		const { SettingsManager } = await loadPi();
		const settings = SettingsManager.create(cwd, agentDir);
		const current = (settings.getGlobalSettings().skills as string[] | undefined) ?? [];
		const matches = current.filter((entry) => resolveSkillEntry(entry, agentDir) === path);
		const positive = matches.filter((entry) => !entry.startsWith("-") && !entry.startsWith("!"));
		const negative = matches.filter((entry) => entry.startsWith("-") || entry.startsWith("!"));
		if (enabled) {
			if (positive.length > 0 && negative.length === 0) return;
			settings.setSkillPaths([...current.filter((entry) => !matches.includes(entry)), path]);
		} else {
			if (positive.length === 0) return;
			settings.setSkillPaths(current.filter((entry) => !positive.includes(entry)));
		}
		await settings.flush();
	});
}
