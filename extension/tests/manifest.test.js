import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";

import { validateExtension } from "../scripts/validate-extension.mjs";

const rootDir = fileURLToPath(new URL("..", import.meta.url));
const manifest = JSON.parse(
	readFileSync(new URL("../manifest.json", import.meta.url), "utf8"),
);

test("every manifest/HTML reference exists inside the extension", () => {
	const result = validateExtension(rootDir);
	assert.ok(result.referencedFiles.includes("background.js"));
	assert.ok(result.referencedFiles.includes("sidebar/sidebar.html"));
	assert.ok(result.referencedFiles.includes("sidebar/sidebar.js"));
	assert.ok(result.referencedFiles.includes("options/options.html"));
	assert.ok(result.referencedFiles.includes("src/ui/content-script.js"));
	assert.ok(
		result.referencedFiles.includes("src/domain/product-detection.js"),
	);
});

test("is a Firefox MV3 add-on with a Gecko id and no service worker", () => {
	assert.equal(manifest.manifest_version, 3);
	assert.ok(manifest.browser_specific_settings.gecko.id);
	assert.ok(manifest.browser_specific_settings.gecko.strict_min_version);
	assert.deepEqual(
		manifest.browser_specific_settings.gecko.data_collection_permissions
			.required,
		["personalCommunications", "websiteContent"],
	);
	assert.equal(manifest.background.type, "module");
	assert.equal(manifest.background.service_worker, undefined);
	assert.ok(manifest.permissions.includes("storage"));
});

test("detection runs before the launcher in the content script injection order", () => {
	const [contentScript] = manifest.content_scripts;
	assert.deepEqual(contentScript.js, [
		"src/domain/product-detection.js",
		"src/ui/content-script.js",
	]);
	for (const match of contentScript.matches) {
		assert.match(match, /^https?:\/\//);
	}
});

test("declares the sidebar, options page and toolbar action", () => {
	assert.equal(manifest.sidebar_action.default_panel, "sidebar/sidebar.html");
	assert.equal(manifest.options_ui.page, "options/options.html");
	assert.ok(manifest.action.default_title);
	assert.ok(manifest.icons["48"]);
});
