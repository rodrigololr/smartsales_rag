/**
 * Resolves the product detected on the page against the SmartSales catalog.
 * The page SKU is authoritative when it exists in the catalog; otherwise a
 * lexical title match may anchor the conversation. When neither works the turn
 * stays in catalog mode — never anchored to an invented SKU (R01).
 *
 * @typedef {import("../infrastructure/settings.js").DetectedProductContext} DetectedProductContext
 * @typedef {import("../infrastructure/gateway-api.js").CatalogProduct} CatalogProduct
 * @typedef {Object} ProductContext
 * @property {CatalogProduct | null} product
 * @property {DetectedProductContext | null} detection
 * @property {"sku" | "name" | null} resolvedBy
 */

import {
	catalogSearchQueries,
	chooseCatalogMatch,
} from "../domain/product-match.js";
import { ApiError } from "../infrastructure/gateway-api.js";

/**
 * @param {{
 *   api: { getProduct: (sku: string, init?: { signal?: AbortSignal }) => Promise<CatalogProduct>, listProducts: (query?: Record<string, unknown>, init?: { signal?: AbortSignal }) => Promise<{ items: CatalogProduct[] }> },
 *   detection: DetectedProductContext | null,
 *   signal?: AbortSignal,
 * }} input
 * @returns {Promise<ProductContext>}
 */
export async function resolveProductContext({ api, detection, signal }) {
	if (!detection) return { product: null, detection: null, resolvedBy: null };

	if (detection.sku) {
		try {
			const product = await api.getProduct(detection.sku, { signal });
			return { product, detection, resolvedBy: "sku" };
		} catch (error) {
			// An unknown SKU is normal on third-party storefronts: try the title.
			if (!(error instanceof ApiError) || error.status !== 404) throw error;
		}
	}

	if (!detection.name) return { product: null, detection, resolvedBy: null };

	// The storefront title often has a shop suffix; the Gateway does substring
	// matching, so try progressively shorter prefixes until one finds candidates.
	for (const query of catalogSearchQueries(detection.name, detection.brand)) {
		const catalogPage = await api.listProducts(
			{ q: query, pageSize: 8 },
			{ signal },
		);
		const product = chooseCatalogMatch(detection.name, catalogPage.items);
		if (product) return { product, detection, resolvedBy: "name" };
	}
	return { product: null, detection, resolvedBy: null };
}
