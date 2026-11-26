/**
 * Browser storage adapters for settings and the short-lived session id.
 * Everything here is pure except the repository methods, which receive the
 * storage areas by dependency injection (DIP).
 *
 * @typedef {import("../domain/chat-events.js").VoltageType} VoltageType
 * @typedef {"127V" | "220V" | null} PreferredVoltage
 *
 * @typedef {Object} ExtensionSettings
 * @property {string} apiBaseUrl
 * @property {boolean} showFloatingButton
 * @property {PreferredVoltage} preferredVoltage
 * @property {number | null} budgetMax
 *
 * @typedef {Object} DetectedProductContext
 * @property {string | null} sku
 * @property {string | null} name
 * @property {string | null} brand
 * @property {string} url
 * @property {string} pageTitle
 * @property {"json-ld" | "microdata" | "dom" | "url" | "open-graph"} evidence
 *
 * @typedef {Object} StorageAreaLike
 * @property {(keys?: string | string[] | null) => Promise<Record<string, unknown>>} get
 * @property {(items: Record<string, unknown>) => Promise<void>} set
 * @property {(keys: string | string[]) => Promise<void>} remove
 */

export const DEFAULT_API_BASE_URL = "http://localhost:8000";
export const SETTINGS_STORAGE_KEY = "smartsales:settings";
export const SESSION_STORAGE_KEY = "smartsales:session-id";
export const PENDING_CONTEXT_STORAGE_KEY = "smartsales:pending-product";

/** @type {Readonly<ExtensionSettings>} */
export const DEFAULT_SETTINGS = Object.freeze({
	apiBaseUrl: DEFAULT_API_BASE_URL,
	showFloatingButton: true,
	preferredVoltage: null,
	budgetMax: null,
});

const UUID_PATTERN =
	/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const SKU_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._/-]{0,63}$/;

/**
 * Accepts only an absolute http(s) origin with an optional path prefix. Query,
 * hash and credentials are rejected so the settings page cannot smuggle a
 * different endpoint into the extension.
 *
 * @param {unknown} value
 * @returns {string | null}
 */
export function parseApiBaseUrl(value) {
	if (typeof value !== "string") return null;
	const candidate = value.trim();
	if (!candidate) return null;
	/** @type {URL} */
	let parsed;
	try {
		parsed = new URL(candidate);
	} catch {
		return null;
	}
	if (parsed.protocol !== "http:" && parsed.protocol !== "https:") return null;
	if (parsed.username || parsed.password || parsed.search || parsed.hash)
		return null;
	const path = parsed.pathname.replace(/\/+$/, "");
	return `${parsed.origin}${path === "/" ? "" : path}`;
}

/**
 * @param {unknown} value
 * @returns {PreferredVoltage}
 */
function normalizeVoltage(value) {
	return value === "127V" || value === "220V" ? value : null;
}

/**
 * @param {unknown} value
 * @returns {number | null}
 */
function normalizeBudget(value) {
	if (value === null || value === undefined || value === "") return null;
	const numeric = typeof value === "number" ? value : Number(value);
	if (!Number.isFinite(numeric) || numeric <= 0) return null;
	return Math.round(numeric * 100) / 100;
}

/**
 * @param {unknown} raw
 * @returns {ExtensionSettings}
 */
export function normalizeSettings(raw) {
	const candidate = typeof raw === "object" && raw !== null ? raw : {};
	const source = /** @type {Record<string, unknown>} */ (candidate);
	return {
		apiBaseUrl:
			parseApiBaseUrl(source.apiBaseUrl) ?? DEFAULT_SETTINGS.apiBaseUrl,
		showFloatingButton: source.showFloatingButton !== false,
		preferredVoltage: normalizeVoltage(source.preferredVoltage),
		budgetMax: normalizeBudget(source.budgetMax),
	};
}

/**
 * Content scripts run outside the extension origin, so every value they send
 * is sanitized again before being stored or rendered by the sidebar.
 *
 * @param {unknown} raw
 * @returns {DetectedProductContext | null}
 */
export function normalizeDetectedProduct(raw) {
	if (typeof raw !== "object" || raw === null) return null;
	const source = /** @type {Record<string, unknown>} */ (raw);
	const clean = (value, maxLength) =>
		typeof value === "string"
			? value.replace(/\s+/g, " ").trim().slice(0, maxLength)
			: "";
	const skuCandidate = clean(source.sku, 64);
	const sku = SKU_PATTERN.test(skuCandidate) ? skuCandidate : null;
	const name = clean(source.name, 300) || null;
	if (!sku && !name) return null;
	return {
		sku,
		name,
		brand: clean(source.brand, 120) || null,
		url: clean(source.url, 2048),
		pageTitle: clean(source.pageTitle, 300),
		evidence:
			source.evidence === "json-ld" ||
			source.evidence === "microdata" ||
			source.evidence === "dom" ||
			source.evidence === "url" ||
			source.evidence === "open-graph"
				? source.evidence
				: "open-graph",
	};
}

/**
 * @param {unknown} value
 * @returns {string | null}
 */
export function normalizeSessionId(value) {
	return typeof value === "string" && UUID_PATTERN.test(value) ? value : null;
}

/**
 * @param {{ localArea: StorageAreaLike, sessionArea?: StorageAreaLike }} areas
 */
export function createSettingsRepository({ localArea, sessionArea }) {
	const ephemeral = sessionArea ?? localArea;

	/** @returns {Promise<ExtensionSettings>} */
	async function getSettings() {
		const stored = await localArea.get(SETTINGS_STORAGE_KEY);
		return normalizeSettings(stored[SETTINGS_STORAGE_KEY]);
	}

	return {
		getSettings,

		/**
		 * @param {Partial<ExtensionSettings>} patch
		 * @returns {Promise<ExtensionSettings>}
		 */
		async saveSettings(patch) {
			const current = await getSettings();
			const next = normalizeSettings({ ...current, ...patch });
			await localArea.set({ [SETTINGS_STORAGE_KEY]: next });
			return next;
		},

		/** @returns {Promise<string | null>} */
		async getSessionId() {
			const stored = await ephemeral.get(SESSION_STORAGE_KEY);
			const sessionId = normalizeSessionId(stored[SESSION_STORAGE_KEY]);
			if (!sessionId && stored[SESSION_STORAGE_KEY] !== undefined) {
				await ephemeral.remove(SESSION_STORAGE_KEY);
			}
			return sessionId;
		},

		/** @param {string} sessionId */
		async setSessionId(sessionId) {
			const normalized = normalizeSessionId(sessionId);
			if (!normalized) throw new Error("session_id inválido");
			await ephemeral.set({ [SESSION_STORAGE_KEY]: normalized });
		},

		async clearSessionId() {
			await ephemeral.remove(SESSION_STORAGE_KEY);
		},

		/**
		 * Pending context is scoped to the tab that requested the sidebar, so a
		 * product detected in a background tab cannot leak into another tab.
		 *
		 * @param {unknown} product
		 * @param {number | null} [tabId]
		 */
		async setPendingProduct(product, tabId = null) {
			const normalized = normalizeDetectedProduct(product);
			if (!normalized) return;
			await ephemeral.set({
				[PENDING_CONTEXT_STORAGE_KEY]: {
					product: normalized,
					tabId: Number.isInteger(tabId) ? tabId : null,
				},
			});
		},

		async clearPendingProduct() {
			await ephemeral.remove(PENDING_CONTEXT_STORAGE_KEY);
		},

		/** @returns {Promise<{ product: DetectedProductContext, tabId: number | null } | null>} */
		async takePendingProduct() {
			const stored = await ephemeral.get(PENDING_CONTEXT_STORAGE_KEY);
			if (stored[PENDING_CONTEXT_STORAGE_KEY] === undefined) return null;
			await ephemeral.remove(PENDING_CONTEXT_STORAGE_KEY);
			const raw = stored[PENDING_CONTEXT_STORAGE_KEY];
			if (typeof raw !== "object" || raw === null) return null;
			const candidate = /** @type {Record<string, unknown>} */ (raw);
			// Compatibility with a product stored directly (older payload shape).
			const product = normalizeDetectedProduct(
				Object.hasOwn(candidate, "product") ? candidate.product : candidate,
			);
			if (!product) return null;
			return {
				product,
				tabId: Number.isInteger(candidate.tabId)
					? Number(candidate.tabId)
					: null,
			};
		},
	};
}
