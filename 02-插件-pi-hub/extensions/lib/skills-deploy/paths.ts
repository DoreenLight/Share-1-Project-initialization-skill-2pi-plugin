import { homedir } from "node:os";
import { join, resolve } from "node:path";

/** Default Projects root used as the skills deploy target. */
export const DEFAULT_PROJECTS_ROOT = join(homedir(), "Projects");

/** Unified gallery lives as a first-class project under Projects. */
export const GALLERY_DIR_NAME = "skills-gallery";

export function galleryRoot(projectsRoot = DEFAULT_PROJECTS_ROOT): string {
	return join(resolve(projectsRoot), GALLERY_DIR_NAME);
}

export function catalogPath(projectsRoot = DEFAULT_PROJECTS_ROOT): string {
	return join(galleryRoot(projectsRoot), "catalog.json");
}

export function indexPath(projectsRoot = DEFAULT_PROJECTS_ROOT): string {
	return join(galleryRoot(projectsRoot), "index.html");
}

/** User-editable partition overrides + custom partition definitions. */
export function partitionsConfigPath(projectsRoot = DEFAULT_PROJECTS_ROOT): string {
	return join(galleryRoot(projectsRoot), "partitions.json");
}

/** Last local gallery server URL (written on /skills-deploy open). */
export function lastServerPath(projectsRoot = DEFAULT_PROJECTS_ROOT): string {
	return join(galleryRoot(projectsRoot), "last-server.json");
}

export function hubRoot(projectsRoot = DEFAULT_PROJECTS_ROOT): string {
	return join(resolve(projectsRoot), "skills-hub");
}

export function resolveUnderHome(input: string): string {
	const trimmed = input.trim();
	if (trimmed === "~") return homedir();
	if (trimmed.startsWith("~/")) return join(homedir(), trimmed.slice(2));
	return resolve(trimmed);
}
