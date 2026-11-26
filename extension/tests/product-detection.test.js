import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";

const source = readFileSync(
	new URL("../src/domain/product-detection.js", import.meta.url),
	"utf8",
);
const sandbox = { console, URL };
vm.runInNewContext(source, sandbox, { filename: "product-detection.js" });
const detection = sandbox.SmartSalesProductDetection;

/**
 * @param {Partial<{ url: string, title: string, metas: Record<string, string>, jsonLd: string[], microdata: { sku: string, name: string, brand: string }, dataSku: string }>} [overrides]
 */
function snapshot(overrides = {}) {
	return {
		url: "https://shop.example/p/airfryer",
		title: "Airfryer | Loja Exemplo",
		metas: {},
		jsonLd: [],
		microdata: { sku: "", name: "", brand: "" },
		dataSku: "",
		...overrides,
	};
}

const jsonLdProduct = JSON.stringify({
	"@context": "https://schema.org",
	"@graph": [
		{ "@type": "BreadcrumbList", itemListElement: [] },
		{
			"@type": "Product",
			sku: "AF-400-220V",
			name: "Airfryer Mondial 4 Litros 220V",
			brand: { "@type": "Brand", name: "Mondial" },
		},
	],
});

test("reads JSON-LD Product from @graph", () => {
	const product = detection.detectProduct(
		snapshot({ jsonLd: [jsonLdProduct] }),
	);
	assert.equal(product.sku, "AF-400-220V");
	assert.equal(product.name, "Airfryer Mondial 4 Litros 220V");
	assert.equal(product.brand, "Mondial");
	assert.equal(product.evidence, "json-ld");
});

test("accepts @type arrays and tolerates malformed JSON-LD", () => {
	const product = detection.detectProduct(
		snapshot({
			jsonLd: [
				"{ broken",
				JSON.stringify({
					"@type": ["Product", "Thing"],
					productID: "SKU-2",
					name: "Produto 2",
				}),
			],
		}),
	);
	assert.equal(product.sku, "SKU-2");
	assert.equal(product.name, "Produto 2");
});

test("reads Open Graph product metadata", () => {
	const product = detection.detectProduct(
		snapshot({
			metas: {
				"og:type": "product",
				"og:title": "Airfryer 4L | Loja",
				"product:retailer_item_id": "AF-400-220V",
				"product:brand": "Mondial",
			},
		}),
	);
	assert.equal(product.sku, "AF-400-220V");
	assert.equal(product.name, "Airfryer 4L | Loja");
	assert.equal(product.brand, "Mondial");
	assert.equal(product.evidence, "open-graph");
});

test("a product SKU meta tag is enough evidence even without og:type", () => {
	const product = detection.detectProduct(
		snapshot({
			metas: { "product:sku": "CF-15B-127V", "og:title": "Cafeteira" },
		}),
	);
	assert.equal(product.sku, "CF-15B-127V");
	assert.equal(product.evidence, "open-graph");
});

test("reads microdata and data-sku fallbacks", () => {
	const microdata = detection.detectProduct(
		snapshot({
			microdata: {
				sku: "AF-550-220V",
				name: "Airfryer 5,5L",
				brand: "Mondial",
			},
		}),
	);
	assert.equal(microdata.sku, "AF-550-220V");
	assert.equal(microdata.evidence, "microdata");

	const dom = detection.detectProduct(snapshot({ dataSku: "NB-NX15-BIV" }));
	assert.equal(dom.sku, "NB-NX15-BIV");
	assert.equal(dom.evidence, "dom");
});

test("recognizes the explicit SmartSales /produto/<SKU> route", () => {
	const product = detection.detectProduct(
		snapshot({
			url: "https://shop.example/produto/AF-400-220V?utm=1",
			title: "Airfryer Mondial 4 Litros 220V — SmartSales RAG",
		}),
	);
	assert.equal(product.sku, "AF-400-220V");
	assert.equal(product.evidence, "url");
});

test("does not flag a generic page as a product page", () => {
	assert.equal(
		detection.detectProduct(
			snapshot({ metas: { "og:title": "Blog da loja" } }),
		),
		null,
	);
	assert.equal(
		detection.detectProduct(
			snapshot({ url: "https://shop.example/blog/airfryer", title: "Blog" }),
		),
		null,
	);
});

test("falls back to the page name when the published SKU is invalid", () => {
	const product = detection.detectProduct(
		snapshot({
			metas: {
				"og:type": "product",
				"og:title": "Produto sem SKU válido",
				"product:retailer_item_id": "../not-a-sku",
			},
		}),
	);
	assert.equal(product.sku, null);
	assert.equal(product.name, "Produto sem SKU válido");
});

test("normalizes SKUs with the catalog-friendly pattern", () => {
	assert.equal(detection.normalizeSku(" AF-400-220V "), "AF-400-220V");
	assert.equal(detection.normalizeSku("AB_12/3.4-5"), "AB_12/3.4-5");
	assert.equal(detection.normalizeSku("."), null);
	assert.equal(detection.normalizeSku("a".repeat(65)), null);
	assert.equal(detection.normalizeSku(""), null);
});

test("collectPageSnapshot reads only product metadata, scripts and data attributes", () => {
	const metaElement = (key, value, attribute = "property") => ({
		getAttribute: (name) =>
			name === attribute ? key : name === "content" ? value : null,
	});
	const fakeDocument = {
		title: "Airfryer Mondial 4L",
		location: { href: "https://shop.example/p/1" },
		querySelectorAll(selector) {
			if (selector.includes("meta[")) {
				return [
					metaElement("og:type", "product"),
					metaElement("og:title", "Airfryer Mondial 4L"),
					metaElement("product:retailer_item_id", "AF-400-220V"),
				];
			}
			if (selector.includes("application/ld+json")) {
				return [{ textContent: jsonLdProduct }];
			}
			return [];
		},
		querySelector() {
			return null;
		},
	};
	const collected = detection.collectPageSnapshot(
		fakeDocument,
		"https://shop.example/p/1",
	);
	assert.equal(collected.metas["og:type"], "product");
	assert.equal(collected.jsonLd.length, 1);
	const product = detection.detectProduct(collected);
	assert.equal(product.sku, "AF-400-220V");
	assert.equal(product.name, "Airfryer Mondial 4 Litros 220V");
});
