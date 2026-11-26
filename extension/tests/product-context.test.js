import assert from "node:assert/strict";
import test from "node:test";

import { resolveProductContext } from "../src/application/product-context.js";
import { ApiError } from "../src/infrastructure/gateway-api.js";

const product = {
	sku: "AF-400-220V",
	name: "Airfryer Mondial 4 Litros 220V",
};

/**
 * @param {{ product?: any, searchItems?: any[], getError?: any }} [options]
 */
function makeApi(options = {}) {
	const calls = { getProduct: [], listProducts: [] };
	return {
		calls,
		async getProduct(sku) {
			calls.getProduct.push(sku);
			if (options.getError) throw options.getError;
			return options.product ?? product;
		},
		async listProducts(query) {
			calls.listProducts.push(query);
			return {
				items: options.searchItems ?? [],
				page: 1,
				page_size: 8,
				total: 0,
			};
		},
	};
}

test("uses the page SKU when the catalog knows it", async () => {
	const api = makeApi();
	const resolved = await resolveProductContext({
		api,
		detection: {
			sku: "AF-400-220V",
			name: "Airfryer | Loja",
			brand: null,
			url: "https://shop.example/p",
			pageTitle: "",
			evidence: "json-ld",
		},
	});
	assert.equal(resolved.product.sku, "AF-400-220V");
	assert.equal(resolved.resolvedBy, "sku");
	assert.deepEqual(api.calls.getProduct, ["AF-400-220V"]);
	assert.equal(api.calls.listProducts.length, 0);
});

test("falls back to a lexical title match when the SKU is unknown", async () => {
	const api = makeApi({
		getError: new ApiError(404, "PRODUCT_NOT_FOUND", "not found"),
		searchItems: [
			{ sku: "AF-550-220V", name: "Airfryer Mondial 5,5 Litros 220V" },
			{ sku: "AF-400-220V", name: "Airfryer Mondial 4 Litros 220V" },
		],
	});
	const resolved = await resolveProductContext({
		api,
		detection: {
			sku: "EXTERNAL-123",
			name: "Airfryer Mondial 4 Litros 220V — Loja Exemplo",
			brand: "Mondial",
			url: "https://shop.example/p",
			pageTitle: "",
			evidence: "json-ld",
		},
	});
	assert.equal(resolved.product.sku, "AF-400-220V");
	assert.equal(resolved.resolvedBy, "name");
	assert.deepEqual(api.calls.listProducts, [
		{ q: "Airfryer Mondial 4 Litros 220V", pageSize: 8 },
	]);
});

test("shortens the catalog query until the substring search finds a candidate", async () => {
	const calls = [];
	const api = {
		async getProduct() {
			throw new ApiError(404, "PRODUCT_NOT_FOUND", "not found");
		},
		async listProducts(query) {
			calls.push(query);
			if (query.q === "Airfryer Mondial 4") {
				return {
					items: [
						{
							sku: "AF-400-220V",
							name: "Airfryer Mondial 4 Litros 220V",
						},
					],
					page: 1,
					page_size: 8,
					total: 1,
				};
			}
			return { items: [], page: 1, page_size: 8, total: 0 };
		},
	};
	const resolved = await resolveProductContext({
		api,
		detection: {
			sku: "EXTERNAL-123",
			name: "Airfryer Mondial 4 Litros 220V — Loja Exemplo",
			brand: "Mondial",
			url: "https://shop.example/p",
			pageTitle: "",
			evidence: "json-ld",
		},
	});
	assert.equal(resolved.product.sku, "AF-400-220V");
	assert.ok(calls.length >= 2);
	assert.equal(calls.at(-1).q, "Airfryer Mondial 4");
});

test("stays in catalog mode when neither SKU nor title matches", async () => {
	const api = makeApi({
		getError: new ApiError(404, "PRODUCT_NOT_FOUND", "not found"),
		searchItems: [{ sku: "OTHER", name: "Cafeteira Elétrica" }],
	});
	const detection = {
		sku: "EXTERNAL-123",
		name: "Galaxy S24 Ultra",
		brand: null,
		url: "https://shop.example/p",
		pageTitle: "",
		evidence: "json-ld",
	};
	const resolved = await resolveProductContext({ api, detection });
	assert.equal(resolved.product, null);
	assert.equal(resolved.detection, detection);
	assert.equal(resolved.resolvedBy, null);
});

test("does not call the catalog without a name when the SKU is unknown", async () => {
	const api = makeApi({
		getError: new ApiError(404, "PRODUCT_NOT_FOUND", "not found"),
	});
	const resolved = await resolveProductContext({
		api,
		detection: {
			sku: "EXTERNAL-123",
			name: null,
			brand: null,
			url: "https://shop.example/p",
			pageTitle: "",
			evidence: "json-ld",
		},
	});
	assert.equal(resolved.product, null);
	assert.equal(api.calls.listProducts.length, 0);
});

test("propagates catalog transport failures", async () => {
	const api = makeApi({
		getError: new ApiError(503, "SERVICE_UNAVAILABLE", "down"),
	});
	await assert.rejects(
		() =>
			resolveProductContext({
				api,
				detection: {
					sku: "AF-400-220V",
					name: "Airfryer",
					brand: null,
					url: "https://shop.example/p",
					pageTitle: "",
					evidence: "json-ld",
				},
			}),
		(error) => error instanceof ApiError && error.status === 503,
	);
});

test("returns an empty context for no detection", async () => {
	const api = makeApi();
	const resolved = await resolveProductContext({ api, detection: null });
	assert.deepEqual(resolved, {
		product: null,
		detection: null,
		resolvedBy: null,
	});
});
