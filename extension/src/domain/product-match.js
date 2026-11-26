/**
 * Lexical matching between a product name found on the page and the SmartSales
 * catalog. No network and no inference: this only decides whether the page
 * product has a likely counterpart in the local catalog.
 *
 * @typedef {{ name: string }} NamedProduct
 */

const STOPWORDS = new Set([
	"a",
	"as",
	"o",
	"os",
	"de",
	"da",
	"das",
	"do",
	"dos",
	"e",
	"em",
	"com",
	"para",
	"por",
	"the",
	"and",
	"with",
	"of",
]);

/**
 * @param {unknown} value
 * @returns {string}
 */
export function normalizeProductName(value) {
	return String(value ?? "")
		.normalize("NFD")
		.replace(/[\u0300-\u036f]/g, "")
		.toLowerCase()
		.replace(/[^a-z0-9]+/g, " ")
		.replace(/\s+/g, " ")
		.trim();
}

/**
 * @param {string} normalizedName
 * @returns {Set<string>}
 */
function meaningfulTokens(normalizedName) {
	const tokens = normalizedName
		.split(" ")
		.filter((token) => token.length > 1 || /\d/.test(token));
	const filtered = tokens.filter((token) => !STOPWORDS.has(token));
	return new Set(filtered.length ? filtered : tokens);
}

/**
 * Dice coefficient over meaningful tokens, with a containment bonus for store
 * titles such as "Airfryer 4L Mondial | Loja Exemplo".
 *
 * @param {string} left
 * @param {string} right
 * @returns {number}
 */
export function nameSimilarity(left, right) {
	const a = normalizeProductName(left);
	const b = normalizeProductName(right);
	if (!a || !b) return 0;
	if (a === b) return 1;
	if (a.includes(b) || b.includes(a)) {
		const shortest = Math.min(a.length, b.length);
		const longest = Math.max(a.length, b.length);
		const ratio = shortest / longest;
		// "Airfryer" inside a full product title is too generic to anchor a page;
		// require a substantial overlap before applying the containment bonus.
		if (ratio >= 0.5) return 0.85 + 0.13 * ratio;
	}
	const tokensA = meaningfulTokens(a);
	const tokensB = meaningfulTokens(b);
	if (!tokensA.size || !tokensB.size) return 0;
	let intersection = 0;
	for (const token of tokensA) {
		if (tokensB.has(token)) intersection += 1;
	}
	return (2 * intersection) / (tokensA.size + tokensB.size);
}

/**
 * The Gateway's catalog search is a case-insensitive substring match over the
 * product name. A storefront title often appends the shop name, so the full
 * title is useless as `q`; these candidates are progressively shorter prefixes
 * of the most product-like segment.
 *
 * @param {unknown} detectedName
 * @param {unknown} [brand]
 * @returns {string[]}
 */
export function catalogSearchQueries(detectedName, brand = null) {
	const raw = String(detectedName ?? "")
		.replace(/\s+/g, " ")
		.trim();
	if (!raw) return [];

	const separators = /[|•·—–]|\s+-\s+|::/g;
	const segments = raw
		.split(separators)
		.map((segment) => segment.trim())
		.filter((segment) => segment.length >= 3);
	const primary =
		[...segments].sort((left, right) => right.length - left.length)[0] ?? raw;
	const words = primary.split(" ");
	/** @type {string[]} */
	const queries = [];

	/** @param {string} value */
	const push = (value) => {
		const candidate = value.replace(/\s+/g, " ").trim().slice(0, 200);
		if (!candidate) return;
		const normalized = normalizeProductName(candidate);
		const duplicated = queries.some(
			(query) => normalizeProductName(query) === normalized,
		);
		if (!duplicated) queries.push(candidate);
	};

	push(primary);
	for (const count of [6, 4, 3]) {
		if (words.length > count) push(words.slice(0, count).join(" "));
	}
	for (const segment of segments) {
		if (segment === primary) continue;
		const segmentWords = segment.split(" ");
		if (segmentWords.length >= 2) push(segmentWords.slice(0, 4).join(" "));
	}
	const brandName = String(brand ?? "")
		.replace(/\s+/g, " ")
		.trim();
	if (brandName) push(brandName.split(" ").slice(0, 2).join(" "));
	// E.g. "Airfryer - 4L" → "Airfryer 4L"; useful when the catalog omits the dash.
	push(raw.replace(separators, " "));
	return queries.slice(0, 5);
}

/**
 * Picks the best catalog product for a name detected on the page. Returns
 * `null` when no candidate reaches the threshold, which keeps the turn in
 * catalog mode instead of anchoring it to the wrong SKU.
 *
 * @template {NamedProduct} T
 * @param {string} detectedName
 * @param {T[]} products
 * @param {{ minScore?: number }} [options]
 * @returns {T | null}
 */
export function chooseCatalogMatch(detectedName, products, options = {}) {
	const minScore = options.minScore ?? 0.55;
	if (!detectedName || !Array.isArray(products) || products.length === 0)
		return null;

	let best = null;
	let bestScore = 0;
	let bestExact = false;
	for (const product of products) {
		const score = nameSimilarity(detectedName, product?.name ?? "");
		const exact =
			normalizeProductName(detectedName) ===
			normalizeProductName(product?.name ?? "");
		if (exact && !bestExact) {
			best = product;
			bestScore = score;
			bestExact = true;
		} else if (!bestExact && score > bestScore) {
			best = product;
			bestScore = score;
		}
	}
	return best && bestScore >= minScore ? best : null;
}
