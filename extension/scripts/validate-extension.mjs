#!/usr/bin/env node
/**
 * Static packaging checks for the Firefox add-on. It does not replace
 * `web-ext lint`, but catches broken manifest references and accidental
 * Chrome-only APIs before loading the extension.
 */

import { existsSync, readFileSync, statSync } from "node:fs";
import { dirname, relative, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

const SIDEBAR_HTML = "sidebar/sidebar.html";
const OPTIONS_HTML = "options/options.html";

/**
 * @param {string} path
 * @returns {boolean}
 */
const isFile = (path) => existsSync(path) && statSync(path).isFile();

/**
 * @param {string} rootDir
 * @param {string} relativePath
 * @param {string[]} errors
 */
function requireFile(rootDir, relativePath, errors) {
	if (typeof relativePath !== "string" || !relativePath) {
		errors.push(
			`Caminho inválido no manifest: ${JSON.stringify(relativePath)}`,
		);
		return;
	}
	const absolute = resolve(rootDir, relativePath);
	const insideRoot =
		!relative(rootDir, absolute).startsWith(`..${sep}`) &&
		absolute !== rootDir;
	if (!insideRoot) {
		errors.push(
			`O manifest referencia um caminho fora da extensão: ${relativePath}`,
		);
		return;
	}
	if (!isFile(absolute))
		errors.push(`Arquivo referenciado não existe: ${relativePath}`);
}

/**
 * @param {string} rootDir
 * @param {string} scriptPath
 * @param {string} htmlPath
 * @param {string[]} errors
 */
function checkElementIds(rootDir, scriptPath, htmlPath, errors) {
	const script = readFileSync(resolve(rootDir, scriptPath), "utf8");
	const html = readFileSync(resolve(rootDir, htmlPath), "utf8");
	const htmlIds = new Set(
		[...html.matchAll(/\bid="([^"]+)"/g)].map((match) => match[1]),
	);
	for (const match of script.matchAll(/getElementById\("([^"]+)"\)/g)) {
		if (!htmlIds.has(match[1])) {
			errors.push(
				`${scriptPath} referencia #${match[1]}, ausente em ${htmlPath}.`,
			);
		}
	}
}

/**
 * @param {string} rootDir
 * @param {string[]} referenced
 */
function scanHtmlReferences(rootDir, referenced) {
	for (const htmlPath of [SIDEBAR_HTML, OPTIONS_HTML]) {
		const absolute = resolve(rootDir, htmlPath);
		if (!isFile(absolute)) continue;
		const html = readFileSync(absolute, "utf8");
		const pattern = /(?:src|href)="([^"]+)"/g;
		for (const match of html.matchAll(pattern)) {
			const reference = match[1];
			if (
				reference.startsWith("http://") ||
				reference.startsWith("https://") ||
				reference.startsWith("data:") ||
				reference.startsWith("#")
			) {
				continue;
			}
			const target = resolve(dirname(absolute), reference);
			const relativeTarget = relative(rootDir, target).split(sep).join("/");
			referenced.push(relativeTarget);
			if (!isFile(target)) {
				throw new Error(
					`${htmlPath} referencia um arquivo inexistente: ${reference}`,
				);
			}
		}
	}
}

/**
 * @param {string} rootDir Absolute path of the `extension/` directory.
 * @returns {{ referencedFiles: string[] }}
 */
export function validateExtension(rootDir) {
	const manifestPath = resolve(rootDir, "manifest.json");
	if (!isFile(manifestPath)) throw new Error("manifest.json não encontrado");
	/** @type {Record<string, any>} */
	const manifest = JSON.parse(readFileSync(manifestPath, "utf8"));
	/** @type {string[]} */
	const errors = [];

	if (manifest.manifest_version !== 3)
		errors.push("manifest_version deve ser 3 (MV3).");
	const gecko = manifest.browser_specific_settings?.gecko;
	if (!gecko?.id)
		errors.push(
			"browser_specific_settings.gecko.id é obrigatório no Firefox.",
		);
	if (!gecko?.strict_min_version)
		errors.push("Defina gecko.strict_min_version.");
	if (!gecko?.data_collection_permissions?.required?.length) {
		errors.push(
			"Declare gecko.data_collection_permissions (exigido por novas extensões no Firefox 140+).",
		);
	}
	if (manifest.background?.service_worker) {
		errors.push(
			"Firefox MV3 usa background.scripts; background.service_worker não é portável.",
		);
	}
	if (
		!Array.isArray(manifest.permissions) ||
		!manifest.permissions.includes("storage")
	) {
		errors.push("A permissão storage é necessária para settings/sessão.");
	}
	if (
		!Array.isArray(manifest.host_permissions) ||
		manifest.host_permissions.length === 0
	) {
		errors.push(
			"host_permissions deve cobrir o gateway e as páginas de produto.",
		);
	}

	/** @type {string[]} */
	const referenced = ["manifest.json"];
	for (const script of manifest.background?.scripts ?? []) {
		referenced.push(script);
		requireFile(rootDir, script, errors);
	}
	for (const contentScript of manifest.content_scripts ?? []) {
		for (const file of [
			...(contentScript.js ?? []),
			...(contentScript.css ?? []),
		]) {
			referenced.push(file);
			requireFile(rootDir, file, errors);
		}
	}
	const sidebarPanel = manifest.sidebar_action?.default_panel;
	if (sidebarPanel) {
		referenced.push(sidebarPanel);
		requireFile(rootDir, sidebarPanel, errors);
	}
	const optionsPage = manifest.options_ui?.page;
	if (optionsPage) {
		referenced.push(optionsPage);
		requireFile(rootDir, optionsPage, errors);
	}
	const collectIcons = (value) => {
		if (typeof value === "string") return [value];
		if (value && typeof value === "object") return Object.values(value);
		return [];
	};
	for (const icon of [
		...collectIcons(manifest.icons),
		...collectIcons(manifest.action?.default_icon),
		...collectIcons(manifest.sidebar_action?.default_icon),
	]) {
		referenced.push(icon);
		requireFile(rootDir, icon, errors);
	}

	try {
		scanHtmlReferences(rootDir, referenced);
	} catch (error) {
		errors.push(error instanceof Error ? error.message : String(error));
	}

	checkElementIds(
		rootDir,
		"sidebar/sidebar.js",
		"sidebar/sidebar.html",
		errors,
	);
	checkElementIds(
		rootDir,
		"options/options.js",
		"options/options.html",
		errors,
	);

	const sourceFiles = [
		...referenced.filter((path) => path.endsWith(".js")),
		resolve(rootDir, "src/domain/chat-events.js"),
		resolve(rootDir, "src/domain/chat-state.js"),
		resolve(rootDir, "src/domain/product-match.js"),
		resolve(rootDir, "src/application/chat-session.js"),
		resolve(rootDir, "src/application/product-context.js"),
		resolve(rootDir, "src/infrastructure/gateway-api.js"),
		resolve(rootDir, "src/infrastructure/settings.js"),
		resolve(rootDir, "src/ui/format.js"),
		resolve(rootDir, "src/ui/icons.js"),
	];
	for (const source of new Set(sourceFiles)) {
		const absolute = source.startsWith(rootDir)
			? source
			: resolve(rootDir, source);
		if (!isFile(absolute)) continue;
		const content = readFileSync(absolute, "utf8");
		if (/\bchrome\s*\./.test(content)) {
			errors.push(
				`${relative(rootDir, absolute).split(sep).join("/")} usa a API chrome.*; use browser.* no Firefox.`,
			);
		}
	}

	if (errors.length) {
		throw new Error(`Extensão inválida:\n- ${errors.join("\n- ")}`);
	}
	return { referencedFiles: [...new Set(referenced)] };
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
	const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), "..");
	try {
		const result = validateExtension(rootDir);
		console.log(
			`Extensão válida (${result.referencedFiles.length} arquivos referenciados).`,
		);
	} catch (error) {
		console.error(error instanceof Error ? error.message : error);
		process.exitCode = 1;
	}
}
