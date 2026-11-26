import assert from "node:assert/strict";
import test from "node:test";

import {
	catalogSearchQueries,
	chooseCatalogMatch,
	nameSimilarity,
	normalizeProductName,
} from "../src/domain/product-match.js";

const catalog = [
	{ sku: "AF-400-220V", name: "Airfryer Mondial 4 Litros 220V" },
	{ sku: "AF-550-220V", name: "Airfryer Mondial 5,5 Litros 220V" },
	{ sku: "CF-15B-127V", name: "Cafeteira Elétrica 15 Xícaras 127V" },
];

test("normalizes accents, punctuation and store-title separators", () => {
	assert.equal(
		normalizeProductName("  Airfryer  Mondial — 4L | Loja Exemplo "),
		"airfryer mondial 4l loja exemplo",
	);
	assert.equal(
		normalizeProductName("Cafeteira Elétrica"),
		"cafeteira eletrica",
	);
});

test("scores exact, containment and token overlap", () => {
	assert.equal(nameSimilarity("Cafeteira Elétrica", "cafeteira eletrica"), 1);
	assert.ok(
		nameSimilarity("Airfryer Mondial 4L", "Airfryer Mondial 4L 220V") > 0.85,
	);
	assert.ok(nameSimilarity("Airfryer Mondial 4L", "Cafeteira Elétrica") < 0.2);
	assert.equal(nameSimilarity("", "x"), 0);
});

test("builds progressively shorter catalog queries from a storefront title", () => {
	const queries = catalogSearchQueries(
		"Airfryer Mondial 4 Litros 220V — Loja Exemplo",
		"Mondial",
	);
	assert.equal(queries[0], "Airfryer Mondial 4 Litros 220V");
	assert.ok(queries.includes("Airfryer Mondial 4 Litros"));
	assert.ok(queries.includes("Airfryer Mondial 4"));
	assert.ok(
		!queries.includes("Airfryer Mondial 4 Litros 220V — Loja Exemplo"),
	);
});

test("catalog query candidates are unique and bounded", () => {
	const queries = catalogSearchQueries(
		`Produto ${"muito ".repeat(40)}longo | Loja`,
		"Marca",
	);
	assert.ok(queries.length <= 5);
	assert.ok(queries.every((query) => query.length <= 200));
	assert.equal(
		new Set(queries.map(normalizeProductName)).size,
		queries.length,
	);
	assert.ok(queries.includes("Marca"));
	assert.deepEqual(catalogSearchQueries(""), []);
});

test("chooses the best catalog candidate for a page title", () => {
	const match = chooseCatalogMatch(
		"Airfryer Mondial 4 Litros 220V | Loja Exemplo",
		catalog,
	);
	assert.equal(match?.sku, "AF-400-220V");
});

test("does not anchor to a weak or overly generic title match", () => {
	assert.equal(chooseCatalogMatch("Galaxy S24 Ultra 512GB", catalog), null);
	assert.equal(chooseCatalogMatch("", catalog), null);
	assert.equal(chooseCatalogMatch("Airfryer", []), null);
	assert.equal(chooseCatalogMatch("Airfryer", catalog), null);
});

test("prefers an exact normalized name regardless of catalog order", () => {
	const reordered = [
		{ sku: "OTHER", name: "Airfryer Mondial 5,5 Litros 220V" },
		{ sku: "EXACT", name: "Airfryer Mondial 4 Litros 220V" },
	];
	assert.equal(
		chooseCatalogMatch("airfryer mondial 4 litros 220v", reordered)?.sku,
		"EXACT",
	);
});
