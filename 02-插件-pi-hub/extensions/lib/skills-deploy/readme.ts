import { execFileSync } from "node:child_process";
import {
	existsSync,
	mkdirSync,
	readFileSync,
	statSync,
	writeFileSync,
} from "node:fs";
import { basename, dirname, join, relative, resolve, sep } from "node:path";
import { galleryRoot } from "./paths.ts";

const README_CANDIDATES = [
	"README.md",
	"README.zh-CN.md",
	"README_ZH.md",
	"readme.md",
	"README_EN.md",
	"README.en.md",
];

const MAX_README_BYTES = 120_000;

export interface ReadmeResolveResult {
	markdown: string;
	source: "local-readme" | "local-skill-md" | "github-readme" | "none";
	path?: string;
	url?: string;
}

export function findLocalReadme(skillDir: string): string | null {
	for (const name of README_CANDIDATES) {
		const p = join(skillDir, name);
		if (existsSync(p) && statSync(p).isFile()) return p;
	}
	// parent collection readme is weaker signal — skip here
	return null;
}

export function readGitRemote(repoRoot: string): string | null {
	try {
		const out = execFileSync("git", ["-C", repoRoot, "remote", "get-url", "origin"], {
			encoding: "utf8",
			stdio: ["ignore", "pipe", "pipe"],
		}).trim();
		return out || null;
	} catch {
		return null;
	}
}

export function parseGithubRemote(remote: string): { owner: string; repo: string } | null {
	// https://github.com/a/b.git or git@github.com:a/b.git
	const m =
		remote.match(/github\.com[:/](?<owner>[^/]+)\/(?<repo>[^/.]+?)(?:\.git)?$/i) ||
		remote.match(/github\.com\/(?<owner>[^/]+)\/(?<repo>[^/.]+)/i);
	if (!m?.groups) return null;
	return { owner: m.groups.owner!, repo: m.groups.repo! };
}

export function githubRepoUrl(remote: string | null | undefined): string | undefined {
	if (!remote) return undefined;
	const g = parseGithubRemote(remote);
	if (!g) return undefined;
	return `https://github.com/${g.owner}/${g.repo}`;
}

export function githubReadmeCandidates(
	remote: string,
	relSkillPath: string,
): string[] {
	const g = parseGithubRemote(remote);
	if (!g) return [];
	const rel = relSkillPath.replace(/\\/g, "/").replace(/^\.\//, "");
	const branches = ["main", "master"];
	const files = ["README.md", "README.zh-CN.md", "readme.md"];
	const urls: string[] = [];
	for (const br of branches) {
		for (const f of files) {
			if (rel && rel !== ".") {
				urls.push(`https://raw.githubusercontent.com/${g.owner}/${g.repo}/${br}/${rel}/${f}`);
			}
			// skill root = repo root (single-skill repos like lieflat-charts)
			urls.push(`https://raw.githubusercontent.com/${g.owner}/${g.repo}/${br}/${f}`);
		}
	}
	return urls;
}

export async function fetchText(url: string, timeoutMs = 8000): Promise<string | null> {
	try {
		const res = await fetch(url, {
			headers: { Accept: "text/plain, text/markdown, */*" },
			signal: AbortSignal.timeout(timeoutMs),
		});
		if (!res.ok) return null;
		const buf = Buffer.from(await res.arrayBuffer());
		if (buf.byteLength > MAX_README_BYTES) {
			return buf.subarray(0, MAX_README_BYTES).toString("utf8") + "\n\n…(截断)…\n";
		}
		return buf.toString("utf8");
	} catch {
		return null;
	}
}

function cachePath(projectsRoot: string, url: string): string {
	const safe = url.replace(/^https?:\/\//, "").replace(/[^\w.-]+/g, "_");
	return join(galleryRoot(projectsRoot), "cache", "github", safe.slice(0, 180) + ".md");
}

export async function loadCachedOrFetch(
	projectsRoot: string,
	url: string,
): Promise<string | null> {
	const cache = cachePath(projectsRoot, url);
	if (existsSync(cache)) {
		try {
			return readFileSync(cache, "utf8");
		} catch {
			/* fallthrough */
		}
	}
	const text = await fetchText(url);
	if (text) {
		try {
			mkdirSync(dirname(cache), { recursive: true });
			writeFileSync(cache, text, "utf8");
		} catch {
			/* ignore cache write */
		}
	}
	return text;
}

export async function resolveReadme(options: {
	skillDir: string;
	skillMd: string;
	collectionPath: string;
	relPath?: string;
	githubRemote?: string | null;
	projectsRoot: string;
	/** Allow network fetch for GitHub README. */
	allowNetwork?: boolean;
}): Promise<ReadmeResolveResult> {
	const local = findLocalReadme(options.skillDir);
	if (local) {
		return {
			markdown: readFileLimited(local),
			source: "local-readme",
			path: local,
		};
	}

	// Single-skill repo: collection root README
	const rootReadme = findLocalReadme(options.collectionPath);
	if (rootReadme && (options.relPath === "." || basename(options.skillDir) === basename(options.collectionPath))) {
		return {
			markdown: readFileLimited(rootReadme),
			source: "local-readme",
			path: rootReadme,
		};
	}
	// Also use collection README when skill is the only / primary content at repo root
	if (rootReadme && existsSync(join(options.collectionPath, "SKILL.md"))) {
		return {
			markdown: readFileLimited(rootReadme),
			source: "local-readme",
			path: rootReadme,
		};
	}

	if (options.allowNetwork && options.githubRemote) {
		const urls = githubReadmeCandidates(options.githubRemote, options.relPath || ".");
		for (const url of urls) {
			const text = await loadCachedOrFetch(options.projectsRoot, url);
			if (text && text.trim().length > 40) {
				return { markdown: text, source: "github-readme", url };
			}
		}
	}

	// Fall back to SKILL.md body (strip frontmatter)
	if (existsSync(options.skillMd)) {
		const raw = readFileLimited(options.skillMd);
		const body = stripFrontmatter(raw).trim();
		if (body) {
			return { markdown: body, source: "local-skill-md", path: options.skillMd };
		}
	}

	return { markdown: "", source: "none" };
}

function readFileLimited(path: string): string {
	const st = statSync(path);
	if (st.size <= MAX_README_BYTES) return readFileSync(path, "utf8");
	const fd = readFileSync(path);
	return fd.subarray(0, MAX_README_BYTES).toString("utf8") + "\n\n…(截断)…\n";
}

export function stripFrontmatter(content: string): string {
	if (!content.startsWith("---")) return content;
	const end = content.indexOf("\n---", 3);
	if (end === -1) return content;
	return content.slice(end + 4).replace(/^\r?\n/, "");
}

/**
 * Minimal Markdown → HTML for README-style pages (headers, lists, code, tables, images).
 * Not a full CommonMark implementation — good enough for skill READMEs like lieflat-charts.
 */
export function markdownToHtml(
	md: string,
	opts?: { assetBase?: string; githubBlobBase?: string },
): string {
	const assetBase = opts?.assetBase ? opts.assetBase.replace(/\\/g, "/") : "";
	const ghBase = opts?.githubBlobBase?.replace(/\/$/, "") || "";

	const lines = md.replace(/\r\n/g, "\n").split("\n");
	const out: string[] = [];
	let i = 0;
	let inCode = false;
	let codeLang = "";
	let codeBuf: string[] = [];
	let inUl = false;
	let inOl = false;
	let inTable = false;
	let tableBuf: string[] = [];

	const closeLists = () => {
		if (inUl) {
			out.push("</ul>");
			inUl = false;
		}
		if (inOl) {
			out.push("</ol>");
			inOl = false;
		}
	};
	const flushTable = () => {
		if (!inTable) return;
		out.push(renderTable(tableBuf));
		tableBuf = [];
		inTable = false;
	};

	while (i < lines.length) {
		const line = lines[i]!;

		// fenced code
		const fence = line.match(/^```(\w*)\s*$/);
		if (fence) {
			flushTable();
			closeLists();
			if (!inCode) {
				inCode = true;
				codeLang = fence[1] || "";
				codeBuf = [];
			} else {
				out.push(
					`<pre class="md-code"><code class="language-${escapeHtml(codeLang)}">${escapeHtml(codeBuf.join("\n"))}</code></pre>`,
				);
				inCode = false;
				codeBuf = [];
				codeLang = "";
			}
			i++;
			continue;
		}
		if (inCode) {
			codeBuf.push(line);
			i++;
			continue;
		}

		// table rows
		if (/^\s*\|/.test(line) && line.includes("|")) {
			closeLists();
			inTable = true;
			tableBuf.push(line);
			i++;
			continue;
		}
		if (inTable) flushTable();

		// Raw HTML blocks (GitHub READMEs often embed <table><img>...)
		if (/^\s*</.test(line) && !/^\s*<\//.test(line)) {
			flushTable();
			closeLists();
			const htmlLines = [line];
			i++;
			// pull consecutive HTML-ish lines (allow blank lines inside tables)
			let guard = 0;
			while (i < lines.length && guard < 400) {
				const n = lines[i]!;
				// stop when markdown structure clearly resumes
				if (
					n.trim() &&
					!/^\s*</.test(n) &&
					!/^\s*\|/.test(n) &&
					/^(#{1,6}\s|```|\s*[-*+]\s|\s*\d+\.\s|>)/.test(n)
				) {
					break;
				}
				// stop after a closing block and a blank line if buffer already has content
				htmlLines.push(n);
				i++;
				guard++;
				const joined = htmlLines.join("\n");
				// heuristic: if we closed table/div/p/section and next is blank markdown, ok to end on blank streak
				if (
					/<\/(table|div|section|details|p)>\s*$/i.test(n) &&
					i < lines.length &&
					!(lines[i] || "").trim()
				) {
					// consume one blank
					if (!(lines[i] || "").trim()) {
						i++;
					}
					void joined;
					break;
				}
			}
			out.push(rewriteHtmlChunk(htmlLines.join("\n")));
			continue;
		}

		// empty
		if (!line.trim()) {
			closeLists();
			i++;
			continue;
		}

		// hr
		if (/^(-{3,}|\*{3,}|_{3,})\s*$/.test(line.trim())) {
			closeLists();
			out.push("<hr />");
			i++;
			continue;
		}

		// headings
		const h = line.match(/^(#{1,6})\s+(.*)$/);
		if (h) {
			closeLists();
			const level = h[1]!.length;
			out.push(`<h${level}>${inline(h[2]!)}</h${level}>`);
			i++;
			continue;
		}

		// blockquote
		if (line.startsWith(">")) {
			closeLists();
			const parts = [line.replace(/^>\s?/, "")];
			i++;
			while (i < lines.length && lines[i]!.startsWith(">")) {
				parts.push(lines[i]!.replace(/^>\s?/, ""));
				i++;
			}
			out.push(`<blockquote>${inline(parts.join(" "))}</blockquote>`);
			continue;
		}

		// ul
		if (/^\s*[-*+]\s+/.test(line)) {
			if (inOl) {
				out.push("</ol>");
				inOl = false;
			}
			if (!inUl) {
				out.push("<ul>");
				inUl = true;
			}
			out.push(`<li>${inline(line.replace(/^\s*[-*+]\s+/, ""))}</li>`);
			i++;
			continue;
		}

		// ol
		if (/^\s*\d+\.\s+/.test(line)) {
			if (inUl) {
				out.push("</ul>");
				inUl = false;
			}
			if (!inOl) {
				out.push("<ol>");
				inOl = true;
			}
			out.push(`<li>${inline(line.replace(/^\s*\d+\.\s+/, ""))}</li>`);
			i++;
			continue;
		}

		closeLists();
		// paragraph (merge consecutive non-empty non-special)
		const parts = [line];
		i++;
		while (
			i < lines.length &&
			lines[i]!.trim() &&
			!/^(#{1,6}\s|```|\| ste|\s*[-*+]\s|\s*\d+\.\s|>|(-{3,}|\*{3,}))/.test(lines[i]!) &&
			!/^\s*\|/.test(lines[i]!)
		) {
			// stop if next looks special
			const n = lines[i]!;
			if (/^(#{1,6}\s|```)/.test(n) || /^\s*[-*+]\s+/.test(n) || /^\s*\d+\.\s+/.test(n) || n.startsWith(">") || /^\s*\|/.test(n)) break;
			if (/^(-{3,}|\*{3,}|_{3,})\s*$/.test(n.trim())) break;
			parts.push(n);
			i++;
		}
		out.push(`<p>${inline(parts.join(" "))}</p>`);
	}

	flushTable();
	closeLists();
	if (inCode) {
		out.push(`<pre class="md-code"><code>${escapeHtml(codeBuf.join("\n"))}</code></pre>`);
	}

	return out.join("\n");

	function inline(text: string): string {
		let s = escapeHtml(text);
		// images ![alt](url)
		s = s.replace(/!\[([^\]]*)\]\(([^)]+)\)/g, (_m, alt, src) => {
			const url = rewriteAsset(src.trim());
			return `<img src="${escapeAttr(url)}" alt="${escapeAttr(alt)}" loading="lazy" />`;
		});
		// links [text](url) — mark for in-panel render (no navigation)
		s = s.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (_m, label, href) => {
			const url = rewriteAsset(href.trim());
			return `<a href="${escapeAttr(url)}" data-render-link="1" rel="noopener">${label}</a>`;
		});
		// bold / italic
		s = s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
		s = s.replace(/\*([^*]+)\*/g, "<em>$1</em>");
		s = s.replace(/`([^`]+)`/g, "<code>$1</code>");
		return s;
	}

	function rewriteAsset(src: string): string {
		if (!src) return src;
		if (/^(data:|mailto:|#)/i.test(src)) return src;
		if (/^https?:\/\//i.test(src)) return src;
		const clean = src.replace(/^\.\//, "");
		if (assetBase) {
			const abs = resolve(assetBase, clean);
			return `/api/file?path=${encodeURIComponent(abs)}`;
		}
		if (ghBase) {
			return `${ghBase}/${clean.replace(/^\//, "")}`;
		}
		return src;
	}

	function rewriteHtmlChunk(chunk: string): string {
		// rewrite src/href in embedded HTML; force links to in-panel render
		return chunk
			.replace(/\b(src|href)=(["'])([^"']+)\2/gi, (_m, attr, q, val) => {
				const rewritten = rewriteAsset(String(val).trim());
				return `${attr}=${q}${rewritten}${q}`;
			})
			.replace(/<a\b([^>]*?)>/gi, (_m, attrs) => {
				let a = String(attrs);
				// strip target=_blank so we can intercept
				a = a.replace(/\s*target\s*=\s*(["']?)_blank\1/gi, "");
				if (!/\bdata-render-link\b/i.test(a)) a += ' data-render-link="1"';
				return `<a${a}>`;
			});
	}
}

function renderTable(rows: string[]): string {
	const parsed = rows
		.map((r) =>
			r
				.trim()
				.replace(/^\|/, "")
				.replace(/\|$/, "")
				.split("|")
				.map((c) => c.trim()),
		)
		.filter((r) => r.length > 0);
	if (parsed.length === 0) return "";
	const isSep = (r: string[]) => r.every((c) => /^:?-{3,}:?$/.test(c));
	let head = parsed[0]!;
	let bodyStart = 1;
	if (parsed[1] && isSep(parsed[1])) {
		bodyStart = 2;
	} else {
		head = [];
		bodyStart = 0;
	}
	const thead =
		head.length > 0
			? `<thead><tr>${head.map((c) => `<th>${inlineBasic(c)}</th>`).join("")}</tr></thead>`
			: "";
	const body = parsed
		.slice(bodyStart)
		.filter((r) => !isSep(r))
		.map((r) => `<tr>${r.map((c) => `<td>${inlineBasic(c)}</td>`).join("")}</tr>`)
		.join("");
	return `<div class="md-table-wrap"><table>${thead}<tbody>${body}</tbody></table></div>`;
}

function inlineBasic(text: string): string {
	let s = escapeHtml(text);
	s = s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
	s = s.replace(/`([^`]+)`/g, "<code>$1</code>");
	s = s.replace(/\[([^\]]+)\]\(([^)]+)\)/g, `<a href="$2" target="_blank" rel="noopener">$1</a>`);
	return s;
}

export function escapeHtml(value: string): string {
	return String(value)
		.replace(/&/g, "&amp;")
		.replace(/</g, "&lt;")
		.replace(/>/g, "&gt;")
		.replace(/"/g, "&quot;");
}

export function escapeAttr(value: string): string {
	return escapeHtml(value).replace(/'/g, "&#39;");
}

/** Ensure path is inside root (prevent traversal). */
export function isPathInside(root: string, target: string): boolean {
	const r = resolve(root) + sep;
	const t = resolve(target);
	return t === resolve(root) || t.startsWith(r);
}

export function relativePosix(from: string, to: string): string {
	return relative(from, to).split(sep).join("/");
}
