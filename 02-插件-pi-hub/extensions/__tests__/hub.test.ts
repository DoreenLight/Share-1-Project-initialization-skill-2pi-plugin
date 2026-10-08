/**
 * Unit tests for /hub pure helpers + SettingsManager integration.
 * Run: npx --yes tsx --test ~/.pi/agent/extensions/__tests__/hub.test.ts
 */
import assert from "node:assert/strict";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { after, describe, it } from "node:test";

import { collectSnapshot, extractHeaderComment, packageState, parseSkillMeta } from "../lib/hub/discover.ts";
import {
	disablePackageEntry,
	enablePackageEntry,
	patternFor,
	restoreParkedSkill,
	sourceOf,
	stripMarker,
	toggleLibrarySkill,
	togglePackage,
	toggleResource,
	updatePathArray,
} from "../lib/hub/state.ts";
import type { HubResource } from "../lib/hub/discover.ts";

const temps: string[] = [];
function tempRoot(prefix = "hub-"): { root: string; agentDir: string; cwd: string } {
	const dir = mkdtempSync(join(tmpdir(), prefix));
	temps.push(dir);
	const agentDir = join(dir, "agent");
	const cwd = join(dir, "work");
	mkdirSync(agentDir, { recursive: true });
	mkdirSync(cwd, { recursive: true });
	return { root: dir, agentDir, cwd };
}

function writeSkill(dir: string, name: string, description: string): string {
	const skillDir = join(dir, "skills", name);
	mkdirSync(skillDir, { recursive: true });
	writeFileSync(
		join(skillDir, "SKILL.md"),
		`---\nname: ${name}\ndescription: ${description}\n---\n\n# ${name}\n`,
	);
	return skillDir;
}

after(() => {
	for (const dir of temps) {
		try {
			rmSync(dir, { recursive: true, force: true });
		} catch {
			/* ignore */
		}
	}
});

describe("updatePathArray", () => {
	it("appends a disable marker", () => {
		assert.deepEqual(updatePathArray([], "skills/alpha", false), ["-skills/alpha"]);
	});

	it("flips disable to enable in place", () => {
		assert.deepEqual(updatePathArray(["-skills/alpha"], "skills/alpha", true), ["+skills/alpha"]);
	});

	it("strips previous markers matched via alias (absolute path)", () => {
		const updated = updatePathArray(
			["-skills/alpha", "+extensions/btw.ts"],
			"skills/alpha",
			true,
			["/home/u/.pi/agent/skills/alpha"],
		);
		assert.deepEqual(updated, ["+extensions/btw.ts", "+skills/alpha"]);
	});

	it("normalises windows separators when comparing", () => {
		const updated = updatePathArray(["-skills\\alpha"], "skills/alpha", true);
		assert.deepEqual(updated, ["+skills/alpha"]);
	});
});

describe("stripMarker", () => {
	it("strips all marker prefixes", () => {
		assert.equal(stripMarker("-x"), "x");
		assert.equal(stripMarker("+x"), "x");
		assert.equal(stripMarker("!x"), "x");
		assert.equal(stripMarker("x"), "x");
	});
});

describe("patternFor", () => {
	it("uses path relative to baseDir", () => {
		const res = {
			type: "skill",
			path: "/home/u/.pi/agent/skills/alpha",
			baseDir: "/home/u/.pi/agent",
		} as HubResource;
		assert.equal(patternFor(res, "/home/u/.pi/agent"), "skills/alpha");
	});

	it("falls back to absolute path outside the base", () => {
		const res = {
			type: "skill",
			path: "/home/u/.agents/skills/alpha",
			baseDir: "/home/u/.pi/agent",
		} as HubResource;
		assert.equal(patternFor(res, "/home/u/.pi/agent"), "/home/u/.agents/skills/alpha");
	});
});

describe("package entry conversions", () => {
	it("disable writes empty-array filters, enable reverts to string", () => {
		const disabled = disablePackageEntry("npm:foo/bar");
		assert.deepEqual(disabled, { source: "npm:foo/bar", extensions: [], skills: [], prompts: [], themes: [] });
		assert.equal(enablePackageEntry(disabled), "npm:foo/bar");
		assert.equal(sourceOf("npm:foo/bar"), "npm:foo/bar");
	});

	it("does not allow bulk toggling filtered package entries", () => {
		assert.deepEqual(packageState({ source: "npm:foo", skills: ["sub"] }), {
			enabled: true,
			filtered: true,
			toggleable: false,
		});
		assert.equal(packageState({ source: "npm:foo", extensions: [], skills: [], prompts: [], themes: [] }).toggleable, true);
		assert.equal(packageState({ source: "npm:foo", autoload: false, extensions: [], skills: [], prompts: [], themes: [] }).toggleable, false);
	});
});

describe("parseSkillMeta", () => {
	it("reads name and folded description", () => {
		const { root, agentDir, cwd } = tempRoot();
		const skillDir = writeSkill(agentDir, "alpha", "First line of a rather long description");
		const meta = parseSkillMeta(join(skillDir, "SKILL.md"));
		assert.equal(meta.name, "alpha");
		assert.match(meta.description ?? "", /rather long description/);
		assert.equal(existsSync(join(cwd, "settings.json")), false);
	});

	it("tolerates missing frontmatter", () => {
		const { agentDir } = tempRoot();
		const dir = join(agentDir, "skills", "plain");
		mkdirSync(dir, { recursive: true });
		writeFileSync(join(dir, "SKILL.md"), "# no frontmatter\n");
		assert.deepEqual(parseSkillMeta(join(dir, "SKILL.md")), {});
	});
});

describe("extractHeaderComment", () => {
	it("extracts the leading block comment", () => {
		const { agentDir } = tempRoot();
		const file = join(agentDir, "extensions", "demo.ts");
		mkdirSync(dirnameOf(file), { recursive: true });
		writeFileSync(file, "/**\n * /demo — does demo things.\n *\n * More detail.\n */\nexport default function () {}\n");
		assert.equal(extractHeaderComment(file), "/demo — does demo things.");
	});

	it("finds a doc block placed after the imports", () => {
		const { agentDir } = tempRoot();
		const file = join(agentDir, "extensions", "clear.ts");
		mkdirSync(dirnameOf(file), { recursive: true });
		writeFileSync(
			file,
			'import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";\n\n/**\n * Claude Code-compatible /clear command for Pi.\n *\n * More words.\n */\nexport default function (pi: ExtensionAPI) {}\n',
		);
		assert.equal(extractHeaderComment(file), "Claude Code-compatible /clear command for Pi.");
	});

	it("returns empty for files without comments", () => {
		const { agentDir } = tempRoot();
		const file = join(agentDir, "extensions", "bare.ts");
		mkdirSync(dirnameOf(file), { recursive: true });
		writeFileSync(file, 'import { x } from "y";\nexport default function () { return x; }\n');
		assert.equal(extractHeaderComment(file), "");
	});
});

function dirnameOf(path: string): string {
	return path.slice(0, path.lastIndexOf("/"));
}

describe("snapshot + toggles (SettingsManager integration)", () => {
	it("discovers local skills, parked skills, and extensions", async () => {
		const { agentDir, cwd } = tempRoot("hub-snap-");
		writeSkill(agentDir, "alpha", "Alpha skill for tests");
		const beta = join(agentDir, "skills-disabled", "beta");
		mkdirSync(beta, { recursive: true });
		writeFileSync(join(beta, "SKILL.md"), "---\nname: beta\ndescription: Parked skill\n---\n# beta\n");
		const extDir = join(agentDir, "extensions");
		mkdirSync(extDir, { recursive: true });
		writeFileSync(join(extDir, "demo.ts"), "/** demo extension */\nexport default function () {}\n");
		writeFileSync(join(extDir, "bare.ts"), 'import { x } from "y";\nexport default function () { return x; }\n');

		const snapshot = await collectSnapshot(cwd, agentDir);
		const alpha = snapshot.resources.find((r) => r.name === "alpha");
		assert.ok(alpha, "alpha discovered");
		assert.equal(alpha.type, "skill");
		assert.equal(alpha.enabled, true);
		assert.equal(alpha.origin, "top-level");
		const demo = snapshot.resources.find((r) => r.type === "extension" && r.name === "demo");
		assert.ok(demo, "demo extension discovered");
		assert.equal(demo.description, "demo extension");
		const bare = snapshot.resources.find((r) => r.type === "extension" && r.name === "bare");
		assert.ok(bare, "bare extension discovered");
		assert.equal(bare.description, "extensions/bare.ts");
		assert.deepEqual(snapshot.parked.map((p) => p.name), ["beta"]);
	});

	it("toggleResource writes +/- patterns that pi resolve() honours", async () => {
		const { agentDir, cwd } = tempRoot("hub-toggle-");
		writeSkill(agentDir, "alpha", "Alpha skill for tests");

		const before = await collectSnapshot(cwd, agentDir);
		const alpha = before.resources.find((r) => r.name === "alpha");
		assert.equal(alpha.enabled, true);

		await toggleResource(cwd, agentDir, alpha, false);
		const settings = JSON.parse(readFileSync(join(agentDir, "settings.json"), "utf8"));
		assert.deepEqual(settings.skills, [`-skills/alpha/SKILL.md`]);
		let after = await collectSnapshot(cwd, agentDir);
		assert.equal(after.resources.find((r) => r.name === "alpha").enabled, false);

		await toggleResource(cwd, agentDir, after.resources.find((r) => r.name === "alpha"), true);
		after = await collectSnapshot(cwd, agentDir);
		assert.equal(after.resources.find((r) => r.name === "alpha").enabled, true);
		const settingsAfter = JSON.parse(readFileSync(join(agentDir, "settings.json"), "utf8"));
		assert.deepEqual(settingsAfter.skills, ["+skills/alpha/SKILL.md"]);
	});

	it("rejects project-scope resources", async () => {
		const { agentDir, cwd } = tempRoot("hub-proj-");
		const fake = {
			id: "skill:/x",
			type: "skill",
			path: "/x",
			name: "x",
			description: "",
			enabled: true,
			origin: "top-level",
			scope: "project",
		} as HubResource;
		await assert.rejects(toggleResource(cwd, agentDir, fake, false), /pi config -l/);
	});

	it("toggles package sub-resources and whole packages", async () => {
		const { root, agentDir, cwd } = tempRoot("hub-pkg-");
		const pkgDir = join(root, "mypkg");
		const pkgSkills = join(pkgDir, "skills", "sub");
		const otherPkgSkill = join(pkgDir, "skills", "other");
		mkdirSync(pkgSkills, { recursive: true });
		mkdirSync(otherPkgSkill, { recursive: true });
		writeFileSync(join(pkgDir, "package.json"), JSON.stringify({ name: "mypkg", pi: { skills: ["./skills"] } }));
		writeFileSync(join(pkgSkills, "SKILL.md"), "---\nname: sub\ndescription: Package skill\n---\n# sub\n");
		writeFileSync(join(otherPkgSkill, "SKILL.md"), "---\nname: other\ndescription: Other package skill\n---\n# other\n");

		const { createManagers } = await import("../lib/hub/discover.ts");
		const { settingsManager } = await createManagers(cwd, agentDir);
		settingsManager.setPackages([pkgDir]);
		await settingsManager.flush();

		let snapshot = await collectSnapshot(cwd, agentDir);
		const sub = snapshot.resources.find((r) => r.name === "sub");
		assert.ok(sub, "package skill discovered");
		assert.equal(sub.origin, "package");
		assert.equal(sub.source, pkgDir);
		assert.equal(sub.enabled, true);

		// An unfiltered string package can be toggled as a whole and remains reversible.
		await togglePackage(cwd, agentDir, pkgDir, false);
		snapshot = await collectSnapshot(cwd, agentDir);
		assert.equal(snapshot.resources.find((r) => r.name === "sub").enabled, false);
		assert.equal(snapshot.packages.find((p) => p.source === pkgDir).enabled, false);

		// Enabling one child from a fully disabled package must not enable its siblings.
		await toggleResource(cwd, agentDir, snapshot.resources.find((r) => r.name === "sub"), true);
		let disabledSettings = JSON.parse(readFileSync(join(agentDir, "settings.json"), "utf8"));
		assert.equal(disabledSettings.packages[0].autoload, undefined);
		assert.deepEqual(disabledSettings.packages[0].skills, ["!**", `+${patternFor(sub, agentDir)}`]);
		snapshot = await collectSnapshot(cwd, agentDir);
		assert.equal(snapshot.resources.find((r) => r.name === "sub").enabled, true);
		assert.equal(snapshot.resources.find((r) => r.name === "other").enabled, false);

		// Reset the fixture to exercise the reversible whole-package path below.
		settingsManager.setPackages([pkgDir]);
		await settingsManager.flush();
		await togglePackage(cwd, agentDir, pkgDir, true);
		snapshot = await collectSnapshot(cwd, agentDir);
		assert.equal(snapshot.resources.find((r) => r.name === "sub").enabled, true);

		await toggleResource(cwd, agentDir, snapshot.resources.find((r) => r.name === "sub"), false);
		const settings = JSON.parse(readFileSync(join(agentDir, "settings.json"), "utf8"));
		assert.equal(settings.packages[0].source, pkgDir);
		assert.deepEqual(settings.packages[0].skills, [`-${patternFor(sub, agentDir)}`]);
		snapshot = await collectSnapshot(cwd, agentDir);
		assert.equal(snapshot.resources.find((r) => r.name === "sub").enabled, false);

		await toggleResource(cwd, agentDir, snapshot.resources.find((r) => r.name === "sub"), true);
		snapshot = await collectSnapshot(cwd, agentDir);
		assert.equal(snapshot.resources.find((r) => r.name === "sub").enabled, true);
		assert.equal(snapshot.packages.find((p) => p.source === pkgDir).toggleable, false);
		await assert.rejects(togglePackage(cwd, agentDir, pkgDir, false), /逐项开关/);
	});

	it("includes project-scope packages and their resources", async () => {
		const { agentDir, cwd } = tempRoot("hub-project-pkg-");
		const pkgDir = join(cwd, "project-pkg");
		const skillDir = join(pkgDir, "skills", "project-only");
		mkdirSync(skillDir, { recursive: true });
		mkdirSync(join(cwd, ".pi"), { recursive: true });
		writeFileSync(join(pkgDir, "package.json"), JSON.stringify({ name: "project-pkg", pi: { skills: ["./skills"] } }));
		writeFileSync(join(skillDir, "SKILL.md"), "---\nname: project-only\ndescription: Project package skill\n---\n# project-only\n");

		const { createManagers } = await import("../lib/hub/discover.ts");
		const { settingsManager } = await createManagers(cwd, agentDir);
		settingsManager.setProjectPackages(["../project-pkg"]);
		await settingsManager.flush();

		const snapshot = await collectSnapshot(cwd, agentDir);
		const pkg = snapshot.packages.find((p) => p.source === "../project-pkg");
		assert.ok(pkg, "project package listed");
		assert.equal(pkg.scope, "project");
		assert.equal(pkg.id, "pkg:project:../project-pkg");
		const resource = snapshot.resources.find((r) => r.name === "project-only");
		assert.ok(resource, "project package resource discovered");
		assert.equal(resource.origin, "package");
		assert.equal(resource.scope, "project");
		assert.equal(resource.source, "../project-pkg");
		await assert.rejects(togglePackage(cwd, agentDir, "../project-pkg", false, "project"), /pi config -l/);
	});

	describe("library scope", () => {
		it("marks project-mounted library skills read-only", async () => {
			const { root, agentDir, cwd } = tempRoot("hub-lib-project-");
			const libraryRoot = join(root, "skills-hub", "skills");
			const gamma = join(libraryRoot, "gamma");
			mkdirSync(gamma, { recursive: true });
			writeFileSync(join(gamma, "SKILL.md"), "---\nname: gamma\ndescription: Project mounted\n---\n# gamma\n");
			process.env.PI_HUB_LIBRARY_DIR = libraryRoot;
			try {
				const { createManagers } = await import("../lib/hub/discover.ts");
				const { settingsManager } = await createManagers(cwd, agentDir);
				settingsManager.setProjectSkillPaths(["../../skills-hub/skills/gamma"]);
				await settingsManager.flush();
				const snapshot = await collectSnapshot(cwd, agentDir);
				const entry = snapshot.library.find((s) => s.name === "gamma");
				assert.ok(entry);
				assert.equal(entry.enabled, true);
				assert.equal(entry.scope, "project");
				await assert.rejects(toggleLibrarySkill(cwd, agentDir, gamma, false, "project"), /pi config -l/);
			} finally {
				delete process.env.PI_HUB_LIBRARY_DIR;
			}
		});
	});

	it("serialises concurrent toggles so no update is lost", async () => {
		const { agentDir, cwd } = tempRoot("hub-race-");
		writeSkill(agentDir, "aaa", "A");
		writeSkill(agentDir, "bbb", "B");
		writeSkill(agentDir, "ccc", "C");

		const snapshot = await collectSnapshot(cwd, agentDir);
		const pick = (name: string) => snapshot.resources.find((r) => r.name === name)!;
		await Promise.all([
			toggleResource(cwd, agentDir, pick("aaa"), false),
			toggleResource(cwd, agentDir, pick("bbb"), false),
			toggleResource(cwd, agentDir, pick("ccc"), false),
		]);
		const settings = JSON.parse(readFileSync(join(agentDir, "settings.json"), "utf8"));
		assert.deepEqual(
			[...settings.skills].sort(),
			["-skills/aaa/SKILL.md", "-skills/bbb/SKILL.md", "-skills/ccc/SKILL.md"],
		);
	});

	it("restoreParkedSkill moves a parked skill back and validates names", () => {
		const { agentDir } = tempRoot("hub-restore-");
		const parked = join(agentDir, "skills-disabled", "beta");
		mkdirSync(parked, { recursive: true });
		writeFileSync(join(parked, "SKILL.md"), "---\nname: beta\ndescription: x\n---\n# beta\n");

		const to = restoreParkedSkill(agentDir, "beta");
		assert.equal(existsSync(to), true);
		assert.equal(existsSync(parked), false);

		const parkedFile = join(agentDir, "skills-disabled", "gamma.md");
		writeFileSync(parkedFile, "---\nname: gamma\ndescription: file\n---\n# gamma\n");
		const fileTo = restoreParkedSkill(agentDir, "gamma");
		assert.equal(fileTo, join(agentDir, "skills", "gamma.md"));
		assert.equal(existsSync(fileTo), true);
		assert.equal(existsSync(parkedFile), false);

		assert.throws(() => restoreParkedSkill(agentDir, "../evil"), /非法/);
		assert.throws(() => restoreParkedSkill(agentDir, "missing"), /不存在/);
	});

	it("lists and mounts/unmounts skills-hub library skills", async () => {
		const { root, agentDir, cwd } = tempRoot("hub-lib-");
		const libraryRoot = join(root, "skills-hub", "skills", "gamma");
		mkdirSync(libraryRoot, { recursive: true });
		writeFileSync(join(libraryRoot, "SKILL.md"), "---\nname: gamma\ndescription: Library fixture skill\n---\n# gamma\n");
		process.env.PI_HUB_LIBRARY_DIR = join(root, "skills-hub", "skills");

		try {
			let snapshot = await collectSnapshot(cwd, agentDir);
			const gamma = snapshot.library.find((s) => s.name === "gamma");
			assert.ok(gamma, "library skill discovered");
			assert.equal(gamma.enabled, false);

			await toggleLibrarySkill(cwd, agentDir, gamma.path, true);
			const settings = JSON.parse(readFileSync(join(agentDir, "settings.json"), "utf8"));
			assert.deepEqual(settings.skills, [gamma.path]);
			snapshot = await collectSnapshot(cwd, agentDir);
			assert.equal(snapshot.library.find((s) => s.name === "gamma").enabled, true);

			// mounting is idempotent; unmounting removes only the matching entry
			await toggleLibrarySkill(cwd, agentDir, gamma.path, true);
			await toggleLibrarySkill(cwd, agentDir, gamma.path, false);
			const after = JSON.parse(readFileSync(join(agentDir, "settings.json"), "utf8"));
			assert.deepEqual(after.skills, []);
			assert.equal((await collectSnapshot(cwd, agentDir)).library.find((s) => s.name === "gamma").enabled, false);
		} finally {
			delete process.env.PI_HUB_LIBRARY_DIR;
		}
	});
});
