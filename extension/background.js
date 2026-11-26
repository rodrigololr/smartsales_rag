/**
 * Firefox background event page: owns the toolbar/sidebar gesture and relays
 * the product detected by the content script. It never calls the Gateway.
 */

import {
	SETTINGS_STORAGE_KEY,
	createSettingsRepository,
	normalizeDetectedProduct,
} from "./src/infrastructure/settings.js";

const repository = createSettingsRepository({
	localArea: browser.storage.local,
	sessionArea: browser.storage.session ?? browser.storage.local,
});

const SIDEBAR_PAGE = "sidebar/sidebar.html";

async function ensureSettings() {
	const stored = await browser.storage.local.get(SETTINGS_STORAGE_KEY);
	if (stored[SETTINGS_STORAGE_KEY] === undefined) {
		await repository.saveSettings({});
	}
}

void ensureSettings().catch((error) => {
	console.warn("settings_initialization_failed", error);
});

browser.runtime.onInstalled.addListener(() => {
	void ensureSettings().catch((error) => {
		console.warn("settings_initialization_failed", error);
	});
});

const STANDALONE_URL = () =>
	browser.runtime.getURL(`${SIDEBAR_PAGE}?source=standalone`);

/**
 * Opens the sidebar, falling back to a regular extension tab when Firefox
 * refuses the programmatic open (e.g. outside a user gesture).
 *
 * @param {unknown} [product]
 * @param {number | null} [tabId]
 */
async function openConsultor(product, tabId = null) {
	const detected = normalizeDetectedProduct(product);
	if (detected) await repository.setPendingProduct(detected, tabId);
	else await repository.clearPendingProduct();
	try {
		await browser.sidebarAction.open();
	} catch (error) {
		console.warn("sidebar_open_fallback", error);
		await browser.tabs.create({ url: STANDALONE_URL() });
	}
}

/**
 * @param {{ type: string, product?: unknown, tabId?: number | null }} message
 */
async function broadcastProductContext(message) {
	try {
		await browser.runtime.sendMessage(message);
	} catch {
		// No sidebar/options page open: pending context covers the next open.
	}
}

browser.action.onClicked.addListener(async () => {
	try {
		const [tab] = await browser.tabs.query({
			active: true,
			currentWindow: true,
		});
		let detected = null;
		if (tab?.id !== undefined) {
			try {
				detected = await browser.tabs.sendMessage(tab.id, {
					type: "smartsales:detect-product",
				});
			} catch {
				// No content script on this page (about:, addons.mozilla.org, PDFs...).
			}
		}
		if (detected)
			await repository.setPendingProduct(detected, tab?.id ?? null);
		else await repository.clearPendingProduct();
		await browser.sidebarAction.toggle();
	} catch (error) {
		console.warn("toolbar_sidebar_toggle_failed", error);
		await browser.tabs.create({ url: STANDALONE_URL() });
	}
});

browser.runtime.onMessage.addListener((message, sender, sendResponse) => {
	if (!message || typeof message !== "object") return false;

	if (message.type === "smartsales:open-consultor") {
		const product = normalizeDetectedProduct(message.product);
		void openConsultor(product, sender.tab?.id ?? null)
			.then(async () => {
				await broadcastProductContext({
					type: "smartsales:product-context",
					product,
					tabId: sender.tab?.id ?? null,
				});
				sendResponse({ ok: true });
			})
			.catch((error) => {
				console.warn("open_consultor_failed", error);
				sendResponse({ ok: false });
			});
		return true;
	}

	if (message.type === "smartsales:page-product") {
		const product = normalizeDetectedProduct(message.product);
		if (product) {
			void repository
				.setPendingProduct(product, sender.tab?.id ?? null)
				.catch((error) => {
					console.warn("pending_product_write_failed", error);
				});
		}
		void broadcastProductContext({
			type: "smartsales:product-context",
			product,
			tabId: sender.tab?.id ?? null,
		});
		return false;
	}

	return false;
});
