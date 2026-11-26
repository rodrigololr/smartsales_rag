/**
 * Reads product identity from the current page without sending page content
 * anywhere. Loaded as a classic content script (Manifest V3 content scripts do
 * not support ES modules) and exposed on `globalThis` for the launcher.
 *
 * Evidence, in priority order: JSON-LD `Product`, Open Graph/product meta tags,
 * Product microdata and explicit `data-sku` attributes. A page with none of
 * those is not treated as a product page, so the floating launcher stays out.
 */
(function (root) {
	"use strict";

	const PRODUCT_TYPES = new Set([
		"product",
		"individualproduct",
		"productgroup",
	]);
	const SKU_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._/-]{0,63}$/;
	const MAX_JSON_LD_NODES = 2000;
	const MAX_JSON_LD_DEPTH = 10;

	/**
	 * @param {unknown} value
	 * @returns {string}
	 */
	function cleanText(value) {
		return typeof value === "string" ? value.replace(/\s+/g, " ").trim() : "";
	}

	/**
	 * @param {unknown} value
	 * @returns {string | null}
	 */
	function normalizeSku(value) {
		const candidate = cleanText(value).replace(/[\u200B-\u200D\uFEFF]/g, "");
		return candidate && SKU_PATTERN.test(candidate) ? candidate : null;
	}

	/**
	 * @param {unknown} value
	 * @returns {string | null}
	 */
	function normalizeName(value) {
		const candidate = cleanText(value).slice(0, 300);
		return candidate || null;
	}

	/**
	 * @param {unknown} value
	 * @returns {string | null}
	 */
	function normalizeBrand(value) {
		const candidate = cleanText(value).slice(0, 120);
		return candidate || null;
	}

	/**
	 * The SmartSales storefront exposes the item at `/produto/<SKU>`. This is an
	 * explicit route, not an inference: the segment is validated like any SKU.
	 *
	 * @param {unknown} url
	 * @returns {string | null}
	 */
	function skuFromStoreUrl(url) {
		if (typeof url !== "string" || !url) return null;
		try {
			const { pathname } = new URL(url);
			const match = pathname.match(/\/produto\/([^/]+)\/?$/i);
			if (!match) return null;
			return normalizeSku(decodeURIComponent(match[1]));
		} catch {
			return null;
		}
	}

	/**
	 * @param {unknown} type
	 * @returns {boolean}
	 */
	function isProductType(type) {
		const values = Array.isArray(type) ? type : [type];
		return values.some((value) => {
			if (typeof value !== "string") return false;
			const shortName = value.split(/[/#:]/).pop() || "";
			return PRODUCT_TYPES.has(shortName.toLowerCase());
		});
	}

	/**
	 * @param {unknown} value
	 * @param {Record<string, unknown>[]} output
	 * @param {number} depth
	 */
	function collectProductNodes(value, output, depth) {
		if (depth > MAX_JSON_LD_DEPTH || output.length >= MAX_JSON_LD_NODES)
			return;
		if (Array.isArray(value)) {
			for (const item of value) collectProductNodes(item, output, depth + 1);
			return;
		}
		if (typeof value !== "object" || value === null) return;
		const node = /** @type {Record<string, unknown>} */ (value);
		if (isProductType(node["@type"])) output.push(node);
		for (const [key, child] of Object.entries(node)) {
			if (key === "@context") continue;
			if (typeof child === "object" && child !== null) {
				collectProductNodes(child, output, depth + 1);
			}
		}
	}

	/**
	 * @param {string[]} blocks
	 * @returns {Record<string, unknown>[]}
	 */
	function parseJsonLdProducts(blocks) {
		/** @type {Record<string, unknown>[]} */
		const products = [];
		for (const block of blocks) {
			if (products.length >= MAX_JSON_LD_NODES) break;
			/** @type {unknown} */
			let parsed;
			try {
				parsed = JSON.parse(block);
			} catch {
				// A malformed block is common on real storefronts; other evidence may still exist.
				continue;
			}
			collectProductNodes(parsed, products, 0);
		}
		return products;
	}

	/**
	 * @param {Record<string, unknown>} node
	 * @returns {string | null}
	 */
	function brandFromJsonLd(node) {
		const brand = node.brand;
		if (typeof brand === "string") return normalizeBrand(brand);
		if (typeof brand === "object" && brand !== null) {
			return normalizeBrand(
				/** @type {Record<string, unknown>} */ (brand).name,
			);
		}
		return null;
	}

	/**
	 * @param {Record<string, string>} metas
	 * @param {string[]} keys
	 * @returns {string}
	 */
	function metaValue(metas, keys) {
		for (const key of keys) {
			const value = cleanText(metas[key]);
			if (value) return value;
		}
		return "";
	}

	/**
	 * @param {unknown} value
	 * @returns {unknown}
	 */
	function firstPresent(value) {
		return Array.isArray(value)
			? value.find((item) => cleanText(item))
			: value;
	}

	/**
	 * @typedef {Object} PageSnapshot
	 * @property {string} url
	 * @property {string} title
	 * @property {Record<string, string>} metas
	 * @property {string[]} jsonLd
	 * @property {{ sku: string, name: string, brand: string }} microdata
	 * @property {string} dataSku
	 *
	 * @typedef {Object} DetectedProduct
	 * @property {string | null} sku
	 * @property {string | null} name
	 * @property {string | null} brand
	 * @property {string} url
	 * @property {string} pageTitle
	 * @property {"json-ld" | "microdata" | "dom" | "url" | "open-graph"} evidence
	 */

	/**
	 * Pure detector: receives a serializable page snapshot and returns the
	 * product identity, or `null` when the page is not a product page.
	 *
	 * @param {PageSnapshot} snapshot
	 * @returns {DetectedProduct | null}
	 */
	function detectProduct(snapshot) {
		if (!snapshot || typeof snapshot !== "object") return null;
		const metas =
			snapshot.metas && typeof snapshot.metas === "object"
				? snapshot.metas
				: {};
		const microdata =
			snapshot.microdata && typeof snapshot.microdata === "object"
				? snapshot.microdata
				: { sku: "", name: "", brand: "" };
		const jsonLdProducts = parseJsonLdProducts(
			Array.isArray(snapshot.jsonLd) ? snapshot.jsonLd : [],
		);
		const jsonProduct = jsonLdProducts[0] || null;
		const jsonSku = jsonProduct
			? normalizeSku(
					firstPresent(jsonProduct.sku) ||
						firstPresent(jsonProduct.productID) ||
						firstPresent(jsonProduct.mpn),
				)
			: null;
		const metaSku = normalizeSku(
			metaValue(metas, [
				"product:retailer_item_id",
				"product:sku",
				"og:sku",
				"sku",
			]),
		);
		const microSku = normalizeSku(microdata.sku);
		const domSku = normalizeSku(snapshot.dataSku);
		const urlSku = skuFromStoreUrl(snapshot.url);
		const ogType = metaValue(metas, ["og:type"]);

		const hasEvidence =
			jsonLdProducts.length > 0 ||
			/product/i.test(ogType) ||
			Boolean(metaSku) ||
			Boolean(microSku || cleanText(microdata.name)) ||
			Boolean(domSku) ||
			Boolean(urlSku);
		if (!hasEvidence) return null;

		const name =
			normalizeName(jsonProduct ? jsonProduct.name : null) ||
			normalizeName(
				metaValue(metas, ["og:title", "product:name", "twitter:title"]),
			) ||
			normalizeName(microdata.name) ||
			normalizeName(snapshot.title);
		const sku = jsonSku || metaSku || microSku || domSku || urlSku;
		const brand =
			(jsonProduct ? brandFromJsonLd(jsonProduct) : null) ||
			normalizeBrand(metaValue(metas, ["product:brand", "og:brand"])) ||
			normalizeBrand(microdata.brand);

		if (!sku && !name) return null;

		return {
			sku,
			name,
			brand,
			url: typeof snapshot.url === "string" ? snapshot.url : "",
			pageTitle: cleanText(snapshot.title),
			evidence: jsonLdProducts.length
				? "json-ld"
				: microSku || cleanText(microdata.name)
					? "microdata"
					: domSku
						? "dom"
						: urlSku
							? "url"
							: "open-graph",
		};
	}

	/**
	 * Reads the current document into the serializable snapshot expected by
	 * `detectProduct`. Never reads form values or page text beyond product fields.
	 *
	 * @param {Document} document
	 * @param {string} [url]
	 * @returns {PageSnapshot}
	 */
	function collectPageSnapshot(document, url) {
		/** @type {Record<string, string>} */
		const metas = {};
		const metaElements = document.querySelectorAll(
			"meta[property], meta[name], meta[itemprop]",
		);
		for (const element of metaElements) {
			const key = (
				element.getAttribute("property") ||
				element.getAttribute("name") ||
				element.getAttribute("itemprop") ||
				""
			).toLowerCase();
			/** @type {string | null} */
			const content = element.getAttribute("content");
			if (key && content && !metas[key]) metas[key] = content;
		}

		/** @type {string[]} */
		const jsonLd = [];
		for (const script of document.querySelectorAll(
			'script[type="application/ld+json"]',
		)) {
			const text = script.textContent || "";
			if (text.trim()) jsonLd.push(text);
		}

		/** @param {Element | null} element */
		const readProp = (element) => {
			if (!element) return "";
			return (
				cleanText(element.getAttribute("content")) ||
				cleanText(element.getAttribute("value")) ||
				cleanText(element.textContent)
			);
		};

		let microSku = "";
		let microName = "";
		let microBrand = "";
		const productRoot =
			document.querySelector('[itemtype*="schema.org/Product"]') ||
			document.querySelector('[itemtype*="Product"]');
		if (productRoot) {
			microSku = readProp(productRoot.querySelector('[itemprop="sku"]'));
			microName = readProp(productRoot.querySelector('[itemprop="name"]'));
			const brandElement = productRoot.querySelector('[itemprop="brand"]');
			microBrand =
				readProp(
					brandElement
						? brandElement.querySelector('[itemprop="name"]')
						: null,
				) || readProp(brandElement);
		}

		let dataSku = "";
		for (const selector of ["[data-sku]", "[data-product-sku]"]) {
			const element = document.querySelector(selector);
			if (element) {
				dataSku = element.getAttribute(selector.slice(1, -1)) || "";
				if (dataSku) break;
			}
		}

		return {
			url: url || document.location?.href || "",
			title: document.title || "",
			metas,
			jsonLd,
			microdata: { sku: microSku, name: microName, brand: microBrand },
			dataSku,
		};
	}

	root.SmartSalesProductDetection = Object.freeze({
		detectProduct,
		collectPageSnapshot,
		normalizeSku,
		normalizeName,
	});
})(typeof globalThis !== "undefined" ? globalThis : this);
