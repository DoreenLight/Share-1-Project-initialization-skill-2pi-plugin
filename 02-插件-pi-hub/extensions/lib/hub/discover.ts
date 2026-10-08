/**
 * hub discovery — enumerate pi resources (extensions/skills/prompts/themes),
 * parked skills, and package entries, mirroring what `pi config` shows.
 *
 * Reuses pi's own SettingsManager + DefaultPackageManager so enable/disable
 * state is computed by the same code path that loads resources.
 */
import { closeSync, existsSync, openSync, readdirSync, readSync, statSync } from "node:fs";
import { homedir } from "node:os";
import { basename, join, relative, resolve } from "node:path";
import type { PackageSource, ResolvedResource } from "@earendil-works/pi-coding-agent";

/**
 * pi-coding-agent only exposes an `import` export condition, so plain-node
 * CJS pipelines (tsx tests) cannot require it. Load runtime values lazily
 * via dynamic import, which resolves under both tsx and pi's jiti.
 */
type PiModule = typeof import("@earendil-works/pi-coding-agent");
let piModule: PiModule | null = null;
export async function loadPi(): Promise<PiModule> {
	piModule ??= await import("@earendil-works/pi-coding-agent");
	return piModule;
}

export type ResourceType = "extension" | "skill" | "prompt" | "theme";
export type HubScope = "user" | "project" | "temporary";
export type PackageScope = Exclude<HubScope, "temporary">;

export interface HubTool {
	id: string;
	name: string;
	description: string;
	parameters: unknown;
	promptGuidelines: string[];
	active: boolean;
	sourceInfo: {
		path: string;
		source: string;
		scope: HubScope;
		origin: "package" | "top-level";
		baseDir?: string;
	};
}

export interface HubResource {
	id: string; // `${type}:${path}`
	type: ResourceType;
	path: string; // absolute
	name: string; // display name
	description: string;
	enabled: boolean; // resolved by pi, same semantics as `pi config`
	origin: "top-level" | "package";
	scope: HubScope;
	source?: string; // package source, when origin === "package"
	sourceRoot?: string; // package root directory (metadata.baseDir)
	baseDir?: string; // metadata.baseDir for pattern generation
	core?: boolean; // the hub extension itself
}

export interface ParkedSkill {
	name: string;
	path: string;
	description: string;
}

export interface LibrarySkill {
	name: string;
	path: string;
	description: string;
	enabled: boolean; // path present in settings `skills` (extra location)
	scope: PackageScope | "none";
}

/** Skills repository maintained by /skills-deploy --hub (Projects/skills-hub). */
export function libraryRootDir(): string {
	return process.env.PI_HUB_LIBRARY_DIR ?? join(homedir(), "Projects", "skills-hub", "skills");
}

/** Resolve a settings `skills` entry the way pi does: markers stripped, ~ expanded, relative to agentDir. */
export function resolveSkillEntry(entry: string, agentDir: string): string {
	const stripped = stripMarkerOf(entry);
	const expanded = stripped.startsWith("~") ? join(homedir(), stripped.slice(1)) : stripped;
	return resolve(agentDir, expanded);
}

function stripMarkerOf(entry: string): string {
	return entry.startsWith("!") || entry.startsWith("+") || entry.startsWith("-") ? entry.slice(1) : entry;
}

function scanLibrarySkills(
	agentDir: string,
	settingsSkills: string[],
	projectSettingsSkills: string[] = [],
	projectBaseDir = agentDir,
): LibrarySkill[] {
	const root = libraryRootDir();
	if (!existsSync(root)) return [];
	const mountedEntries = (entries: string[]) =>
		entries.filter((entry) => !entry.startsWith("-") && !entry.startsWith("!"));
	const userEntries = mountedEntries(settingsSkills).map((e) => resolveSkillEntry(e, agentDir));
	const projectEntries = mountedEntries(projectSettingsSkills).map((e) => resolveSkillEntry(e, projectBaseDir));
	const out: LibrarySkill[] = [];
	for (const dirent of readdirSync(root, { withFileTypes: true })) {
		if (dirent.name.startsWith(".")) continue;
		const path = join(root, dirent.name);
		let skillMd: string;
		let name: string;
		if (dirent.isDirectory()) {
			skillMd = join(path, "SKILL.md");
			if (!existsSync(skillMd)) continue;
			name = dirent.name;
		} else if (dirent.name.endsWith(".md")) {
			skillMd = path;
			name = dirent.name.replace(/\.md$/i, "");
		} else {
			continue;
		}
		const meta = parseSkillMeta(skillMd);
		const scope: LibrarySkill["scope"] = projectEntries.includes(path)
			? "project"
			: userEntries.includes(path)
				? "user"
				: "none";
		out.push({
			name: meta.name || name,
			path,
			description: meta.description || "",
			enabled: scope !== "none",
			scope,
		});
	}
	return out.sort((a, b) => a.name.localeCompare(b.name));
}

export interface PackageEntry {
	id: string;
	source: string;
	scope: PackageScope;
	enabled: boolean; // false when fully filtered out via empty arrays
	filtered: boolean; // any object-form filtering present
	toggleable: boolean; // bulk toggling is safe only for unfiltered entries
}

export interface HubSnapshot {
	resources: HubResource[];
	parked: ParkedSkill[];
	library: LibrarySkill[];
	packages: PackageEntry[];
	tools: HubTool[];
	agentDir: string;
	generatedAt: string;
}

export function resolveAgentDir(): string {
	const override = process.env.PI_CODING_AGENT_DIR;
	if (override) return resolve(override);
	return join(homedir(), ".pi", "agent");
}

export async function createManagers(cwd: string, agentDir: string) {
	const { SettingsManager, DefaultPackageManager } = await loadPi();
	const settingsManager = SettingsManager.create(cwd, agentDir);
	const packageManager = new DefaultPackageManager({ cwd, agentDir, settingsManager });
	return { settingsManager, packageManager };
}

/** Read up to `limit` bytes of a text file, tolerating missing files. */
function readHead(path: string, limit = 8192): string {
	let fd: number | undefined;
	try {
		if (limit <= 0 || !existsSync(path) || !statSync(path).isFile()) return "";
		fd = openSync(path, "r");
		const buffer = Buffer.alloc(limit);
		const bytes = readSync(fd, buffer, 0, limit, 0);
		return buffer.toString("utf8", 0, bytes);
	} catch {
		return "";
	} finally {
		if (fd !== undefined) {
			try {
				closeSync(fd);
			} catch {
				/* ignore close errors */
			}
		}
	}
}

/** Parse `name`/`description` from a SKILL.md frontmatter block. */
export function parseSkillMeta(path: string): { name?: string; description?: string } {
	const text = readHead(path);
	const match = /^\uFEFF?---\r?\n([\s\S]*?)\r?\n---/.exec(text);
	if (!match) return {};
	const lines = match[1].split(/\r?\n/);
	const out: { name?: string; description?: string } = {};
	let current: keyof typeof out | null = null;
	for (const line of lines) {
		const kv = /^([A-Za-z-]+):\s*(.*)$/.exec(line);
		if (kv) {
			const key = kv[1].toLowerCase();
			if (key === "name" || key === "description") {
				current = key;
				out[key] = kv[2].trim();
			} else {
				current = null;
			}
		} else if (current && /^[ \t]+\S/.test(line)) {
			out[current] = `${out[current] ?? ""} ${line.trim()}`.trim();
		} else if (line.trim() === "") {
			current = null;
		}
	}
	if (out.description) out.description = out.description.replace(/\s+/g, " ").slice(0, 300);
	return out;
}

/**
 * Extract a short description from an extension file's header comment.
 * Skips leading import/require/code lines, so a doc block placed after
 * the imports (a common style here) is still found.
 */
export function extractHeaderComment(path: string): string {
	const text = readHead(path, 8192);
	const rawLines = text.split(/\r?\n/).slice(0, 40);
	const collected: string[] = [];
	let inBlock = false;
	for (const raw of rawLines) {
		const trimmed = raw.trim();
		if (inBlock) {
			if (trimmed === "*/") break;
			const body = trimmed.replace(/^\*\s?/, "").replace(/\s*\*\/$/, "").trim();
			if (!body) break; // blank comment line ends the first paragraph
			collected.push(body);
			if (collected.length >= 3 || trimmed.endsWith("*/")) break;
			continue;
		}
		if (trimmed.startsWith("/**") || trimmed.startsWith("/*")) {
			inBlock = true;
			const body = trimmed.replace(/^\/\*\*?/, "").replace(/\s*\*\/$/, "").trim();
			if (body) collected.push(body);
			if (trimmed.endsWith("*/")) break;
			continue;
		}
		if (trimmed.startsWith("//")) {
			const body = trimmed.replace(/^\/\/\s?/, "").trim();
			if (body) collected.push(body);
			continue;
		}
		if (collected.length > 0) break; // comment run ended
		if (!trimmed) continue;
		if (/^(import|export|const|let|var|require\()/.test(trimmed)) continue;
		break;
	}
	return collected.join(" ").replace(/\s+/g, " ").slice(0, 300);
}

function describeResource(res: ResolvedResource, type: ResourceType, agentDir: string): { name: string; description: string } {
	const base = basename(res.path);
	if (type === "skill") {
		const skillMd = res.path.endsWith(".md") ? res.path : join(res.path, "SKILL.md");
		const meta = parseSkillMeta(skillMd);
		return {
			name: meta.name || base.replace(/\.md$/i, ""),
			description: meta.description || "",
		};
	}
	if (type === "extension") {
		const description = extractHeaderComment(res.path);
		return {
			name: base.replace(/\.(ts|js)$/i, ""),
			description: description || relative(agentDir, res.path).replace(/^.*?\.\.\//, ""),
		};
	}
	return { name: base.replace(/\.(md|json)$/i, ""), description: "" };
}

function scanParkedSkills(agentDir: string): ParkedSkill[] {
	const parkedDir = join(agentDir, "skills-disabled");
	if (!existsSync(parkedDir)) return [];
	const out: ParkedSkill[] = [];
	for (const entry of readdirSync(parkedDir, { withFileTypes: true })) {
		if (entry.name.startsWith(".")) continue;
		const path = join(parkedDir, entry.name);
		if (entry.isDirectory()) {
			if (!existsSync(join(path, "SKILL.md"))) continue;
			const meta = parseSkillMeta(join(path, "SKILL.md"));
			out.push({ name: entry.name, path, description: meta.description || "" });
		} else if (entry.name.endsWith(".md")) {
			const meta = parseSkillMeta(path);
			out.push({ name: entry.name.replace(/\.md$/i, ""), path, description: meta.description || "" });
		}
	}
	return out.sort((a, b) => a.name.localeCompare(b.name));
}

function sourceOf(entry: PackageSource): string {
	return typeof entry === "string" ? entry : entry.source;
}

export function packageState(entry: PackageSource): { enabled: boolean; filtered: boolean; toggleable: boolean } {
	if (typeof entry === "string") return { enabled: true, filtered: false, toggleable: true };
	const obj = entry as Record<string, unknown>;
	const arrays = ["extensions", "skills", "prompts", "themes"].map((k) =>
		Array.isArray(obj[k]) ? (obj[k] as unknown[]) : undefined,
	);
	const filtered = obj.autoload === false || arrays.some((a) => a !== undefined);
	const allEmpty = arrays.every((a) => a !== undefined && a.length === 0);
	const reversibleDisable = allEmpty && obj.autoload !== false;
	// A fully disabled object produced from an unfiltered package can safely be
	// converted back to its source; other object-form filters must be preserved
	// by toggling individual resources instead of rewriting the package entry.
	return { enabled: !allEmpty, filtered, toggleable: !filtered || reversibleDisable };
}

export async function collectSnapshot(cwd: string, agentDir: string): Promise<HubSnapshot> {
	const { settingsManager, packageManager } = await createManagers(cwd, agentDir);
	const resolved = await packageManager.resolve(async () => "skip" as const);

	const hubPath = resolve(agentDir, "extensions", "hub.ts");
	const resources: HubResource[] = [];
	const typeMap: [ResourceType, ResolvedResource[]][] = [
		["extension", resolved.extensions],
		["skill", resolved.skills],
		["prompt", resolved.prompts],
		["theme", resolved.themes],
	];
	for (const [type, list] of typeMap) {
		for (const res of list) {
			const { name, description } = describeResource(res, type, agentDir);
			resources.push({
				id: `${type}:${res.path}`,
				type,
				path: res.path,
				name,
				description,
				enabled: res.enabled,
				origin: res.metadata.origin,
				scope: res.metadata.scope === "project" ? "project" : res.metadata.scope === "temporary" ? "temporary" : "user",
				source: res.metadata.origin === "package" ? res.metadata.source : undefined,
				sourceRoot: res.metadata.baseDir,
				baseDir: res.metadata.baseDir,
				core: type === "extension" && resolve(res.path) === hubPath,
			});
		}
	}
	resources.sort((a, b) => a.name.localeCompare(b.name));

	const globalSettings = settingsManager.getGlobalSettings();
	const projectSettings = settingsManager.getProjectSettings();
	const configuredPackages: { entry: PackageSource; scope: PackageScope }[] = [
		...(globalSettings.packages ?? []).map((entry) => ({ entry, scope: "user" as const })),
		...(projectSettings.packages ?? []).map((entry) => ({ entry, scope: "project" as const })),
	];
	const seenPackages = new Set<string>();
	const packages: PackageEntry[] = [];
	for (const { entry, scope } of configuredPackages) {
		const source = sourceOf(entry);
		const key = `${scope}\u0000${source}`;
		if (seenPackages.has(key)) continue;
		seenPackages.add(key);
		packages.push({ id: `pkg:${scope}:${source}`, source, scope, ...packageState(entry) });
	}

	return {
		resources,
		parked: scanParkedSkills(agentDir),
		library: scanLibrarySkills(
			agentDir,
			(globalSettings.skills as string[] | undefined) ?? [],
			(projectSettings.skills as string[] | undefined) ?? [],
			join(cwd, ".pi"),
		),
		packages,
		tools: [],
		agentDir,
		generatedAt: new Date().toISOString(),
	};
}
