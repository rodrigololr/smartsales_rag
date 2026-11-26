import assert from "node:assert/strict";
import test from "node:test";

import {
	DEFAULT_SETTINGS,
	PENDING_CONTEXT_STORAGE_KEY,
	SESSION_STORAGE_KEY,
	SETTINGS_STORAGE_KEY,
	createSettingsRepository,
	normalizeDetectedProduct,
	normalizeSessionId,
	normalizeSettings,
	parseApiBaseUrl,
} from "../src/infrastructure/settings.js";
import { fakeStorageArea, uuid } from "./support/storage.js";

test("accepts only absolute http(s) gateway origins", () => {
	assert.equal(
		parseApiBaseUrl("http://localhost:8000"),
		"http://localhost:8000",
	);
	assert.equal(
		parseApiBaseUrl("https://api.example.com/"),
		"https://api.example.com",
	);
	assert.equal(
		parseApiBaseUrl("https://api.example.com/gateway///"),
		"https://api.example.com/gateway",
	);
	assert.equal(parseApiBaseUrl("ftp://example.com"), null);
	assert.equal(parseApiBaseUrl("localhost:8000"), null);
	assert.equal(parseApiBaseUrl("https://user:pass@example.com"), null);
	assert.equal(parseApiBaseUrl("https://example.com/?a=1"), null);
	assert.equal(parseApiBaseUrl("https://example.com/#x"), null);
	assert.equal(parseApiBaseUrl(""), null);
});

test("normalizes settings and rejects out-of-contract filter values", () => {
	assert.deepEqual(normalizeSettings({}), DEFAULT_SETTINGS);
	assert.deepEqual(
		normalizeSettings({
			apiBaseUrl: "https://gateway.example/base/",
			showFloatingButton: false,
			preferredVoltage: "127V",
			budgetMax: "1234.567",
		}),
		{
			apiBaseUrl: "https://gateway.example/base",
			showFloatingButton: false,
			preferredVoltage: "127V",
			budgetMax: 1234.57,
		},
	);
	assert.equal(
		normalizeSettings({ apiBaseUrl: "nope" }).apiBaseUrl,
		DEFAULT_SETTINGS.apiBaseUrl,
	);
	assert.equal(
		normalizeSettings({ preferredVoltage: "380V" }).preferredVoltage,
		null,
	);
	assert.equal(normalizeSettings({ budgetMax: -1 }).budgetMax, null);
	assert.equal(normalizeSettings({ budgetMax: "" }).budgetMax, null);
});

test("sanitizes product context received from a content script", () => {
	assert.deepEqual(
		normalizeDetectedProduct({
			sku: "AF-400-220V",
			name: "  Airfryer   4L ",
			brand: "Mondial",
			url: "https://shop.example/p/1",
			pageTitle: "Airfryer | Loja",
			evidence: "json-ld",
		}),
		{
			sku: "AF-400-220V",
			name: "Airfryer 4L",
			brand: "Mondial",
			url: "https://shop.example/p/1",
			pageTitle: "Airfryer | Loja",
			evidence: "json-ld",
		},
	);
	assert.equal(normalizeDetectedProduct(null), null);
	assert.equal(normalizeDetectedProduct({ sku: "", name: "" }), null);
	assert.equal(
		normalizeDetectedProduct({ sku: "../etc/passwd", name: "X" }).sku,
		null,
	);
	assert.equal(
		normalizeDetectedProduct({ sku: "SKU", evidence: "unknown" }).evidence,
		"open-graph",
	);
});

test("normalizes session ids to UUIDs", () => {
	assert.equal(normalizeSessionId(uuid(1)), uuid(1));
	assert.equal(normalizeSessionId("not-a-uuid"), null);
	assert.equal(normalizeSessionId(42), null);
});

test("repository persists settings, session id and pending product", async () => {
	const local = fakeStorageArea();
	const session = fakeStorageArea();
	const repository = createSettingsRepository({
		localArea: local,
		sessionArea: session,
	});

	assert.deepEqual(await repository.getSettings(), DEFAULT_SETTINGS);

	const saved = await repository.saveSettings({
		apiBaseUrl: "http://localhost:9000/",
		preferredVoltage: "220V",
		showFloatingButton: false,
		budgetMax: 700,
	});
	assert.equal(saved.apiBaseUrl, "http://localhost:9000");
	assert.equal(saved.preferredVoltage, "220V");
	assert.equal(saved.showFloatingButton, false);
	assert.equal(saved.budgetMax, 700);
	assert.deepEqual(local.data[SETTINGS_STORAGE_KEY], saved);

	assert.equal(await repository.getSessionId(), null);
	await repository.setSessionId(uuid(2));
	assert.equal(await repository.getSessionId(), uuid(2));
	assert.equal(session.data[SESSION_STORAGE_KEY], uuid(2));
	await repository.clearSessionId();
	assert.equal(await repository.getSessionId(), null);

	await repository.setPendingProduct(
		{ sku: "SKU-1", name: "Produto", url: "https://x" },
		17,
	);
	assert.deepEqual(session.data[PENDING_CONTEXT_STORAGE_KEY], {
		product: {
			sku: "SKU-1",
			name: "Produto",
			brand: null,
			url: "https://x",
			pageTitle: "",
			evidence: "open-graph",
		},
		tabId: 17,
	});
	const taken = await repository.takePendingProduct();
	assert.equal(taken.product.sku, "SKU-1");
	assert.equal(taken.tabId, 17);
	assert.equal(await repository.takePendingProduct(), null);

	await repository.setPendingProduct({ sku: "SKU-2", name: "Outro" });
	assert.equal(session.data[PENDING_CONTEXT_STORAGE_KEY].tabId, null);
	await repository.clearPendingProduct();
	assert.equal(
		Object.hasOwn(session.data, PENDING_CONTEXT_STORAGE_KEY),
		false,
	);
});

test("repository reads a legacy pending product without tab scope", async () => {
	const local = fakeStorageArea();
	const session = fakeStorageArea({
		[PENDING_CONTEXT_STORAGE_KEY]: {
			sku: "SKU-LEGACY",
			name: "Legado",
			url: "https://x",
		},
	});
	const repository = createSettingsRepository({
		localArea: local,
		sessionArea: session,
	});
	const pending = await repository.takePendingProduct();
	assert.equal(pending.product.sku, "SKU-LEGACY");
	assert.equal(pending.tabId, null);
});

test("repository removes a corrupt stored session id", async () => {
	const local = fakeStorageArea();
	const session = fakeStorageArea({ [SESSION_STORAGE_KEY]: "broken" });
	const repository = createSettingsRepository({
		localArea: local,
		sessionArea: session,
	});
	assert.equal(await repository.getSessionId(), null);
	assert.equal(Object.hasOwn(session.data, SESSION_STORAGE_KEY), false);
});
