/**
 * Keep development-only files out of the packaged add-on.
 * `web-ext lint` and `web-ext build` both read this file.
 */
export default {
	ignoreFiles: [
		"tests/**",
		"scripts/**",
		"package.json",
		"README.md",
		".gitignore",
		"web-ext-artifacts/**",
	],
	build: {
		overwriteDest: true,
	},
};
