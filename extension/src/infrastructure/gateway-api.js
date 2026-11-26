/**
 * Infrastructure adapter for the SmartSales Gateway (`/api/v1`).
 *
 * The extension never imports Gateway code: this file mirrors the public
 * OpenAPI/SSE contract and is the only place that performs HTTP or parses SSE.
 *
 * @typedef {import("../domain/chat-events.js").StreamEvent} StreamEvent
 * @typedef {import("../domain/chat-events.js").ManualCitation} ManualCitation
 * @typedef {import("../domain/chat-events.js").ProductCardData} ProductCardData
 * @typedef {import("../domain/chat-events.js").RecommendationType} RecommendationType
 * @typedef {import("../domain/chat-events.js").MarketplaceType} MarketplaceType
 * @typedef {"127V" | "220V" | "BIVOLT" | "N/A"} VoltageType
 *
 * @typedef {Object} CatalogProduct
 * @property {string} sku
 * @property {string} name
 * @property {number} price
 * @property {number} stock_quantity
 * @property {VoltageType} voltage
 * @property {number | null} capacity_liters
 * @property {number | null} power_watts
 * @property {string} image_url
 * @property {MarketplaceType} marketplace
 * @property {string} checkout_url
 * @property {string} category
 * @property {string} subcategory
 * @property {string} brand
 * @property {Record<string, unknown>} specs_json
 * @property {string | null} [description]
 * @property {string} updated_at
 *
 * @typedef {Object} CatalogPage
 * @property {CatalogProduct[]} items
 * @property {number} page
 * @property {number} page_size
 * @property {number} total
 *
 * @typedef {Object} SessionSnapshot
 * @property {string} session_id
 * @property {boolean} restored
 * @property {{ id: string, role: "user" | "assistant", content: string }[]} history
 * @property {number} expires_in_seconds
 *
 * @typedef {Object} CheckoutRequest
 * @property {string} session_id
 * @property {string} message_id
 * @property {string} sku
 * @property {RecommendationType} recommendation_type
 * @property {number} quantity
 * @property {number} displayed_price
 *
 * @typedef {Object} Checkout
 * @property {string} checkout_event_id
 * @property {"CONFIRMED"} status
 * @property {string} sku
 * @property {string} product_name
 * @property {string} voltage
 * @property {string} marketplace
 * @property {string} redirect_checkout_url
 * @property {number} quantity
 * @property {number} confirmed_unit_price
 * @property {number} total_amount
 * @property {number} remaining_stock
 * @property {string} message
 *
 * @typedef {Object} CheckoutConflict
 * @property {string} checkout_event_id
 * @property {"OUT_OF_STOCK" | "PRICE_CHANGED"} status
 * @property {string} sku
 * @property {number} current_price
 * @property {number} current_stock
 * @property {null} redirect_checkout_url
 * @property {string} message
 */

import { SSEParser } from "../domain/chat-events.js";
import { DEFAULT_API_BASE_URL, parseApiBaseUrl } from "./settings.js";

const DEFAULT_RETRY_AFTER_SECONDS = 1;
const MAX_TURN_IN_PROGRESS_WAITS = 3;
const NETWORK_ERROR_MESSAGE =
	"Não foi possível conectar ao consultor. Verifique a URL da API nas opções da extensão.";
const GENERIC_HTTP_ERROR = "O consultor não conseguiu atender a solicitação.";

export class ApiError extends Error {
	/**
	 * @param {number} status
	 * @param {string} code
	 * @param {string} message
	 * @param {{ retryAfterSeconds?: number | null }} [options]
	 */
	constructor(status, code, message, options = {}) {
		super(message);
		this.name = "ApiError";
		this.status = status;
		this.code = code;
		this.retryAfterSeconds = options.retryAfterSeconds ?? null;
	}
}

/** Connection lost before `done`: the same client_request_id may be resent once. */
export class StreamInterruptedError extends Error {
	constructor() {
		super("A conexão com o consultor caiu antes do fim da resposta.");
		this.name = "StreamInterruptedError";
	}
}

/**
 * @param {unknown} error
 * @returns {boolean}
 */
const isAbort = (error) =>
	error instanceof Error && error.name === "AbortError";

/**
 * @param {number} milliseconds
 * @param {AbortSignal} [signal]
 * @returns {Promise<void>}
 */
const defaultWait = (milliseconds, signal) =>
	new Promise((resolve, reject) => {
		const timer = setTimeout(resolve, milliseconds);
		if (!signal) return;
		signal.addEventListener(
			"abort",
			() => {
				clearTimeout(timer);
				reject(signal.reason);
			},
			{ once: true },
		);
	});

/**
 * @returns {string}
 */
export function createRequestId() {
	if (typeof globalThis.crypto?.randomUUID === "function") {
		return globalThis.crypto.randomUUID();
	}
	return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(
		/[xy]/g,
		(character) => {
			const random = (Math.random() * 16) | 0;
			const value = character === "x" ? random : (random & 0x3) | 0x8;
			return value.toString(16);
		},
	);
}

/**
 * @param {unknown} body
 * @returns {body is CheckoutConflict}
 */
const isCheckoutConflict = (body) => {
	if (typeof body !== "object" || body === null) return false;
	const candidate = /** @type {Record<string, unknown>} */ (body);
	return (
		(candidate.status === "PRICE_CHANGED" ||
			candidate.status === "OUT_OF_STOCK") &&
		Number.isFinite(candidate.current_price) &&
		Number.isFinite(candidate.current_stock)
	);
};

/**
 * @param {Response} response
 * @returns {Promise<ApiError>}
 */
async function toApiError(response) {
	let code = `HTTP_${response.status}`;
	let message = response.statusText || GENERIC_HTTP_ERROR;
	try {
		/** @type {unknown} */
		const body = await response.json();
		if (typeof body === "object" && body !== null) {
			const envelope = /** @type {Record<string, unknown>} */ (body).error;
			if (typeof envelope === "object" && envelope !== null) {
				const details = /** @type {Record<string, unknown>} */ (envelope);
				if (typeof details.code === "string") code = details.code;
				if (typeof details.message === "string") message = details.message;
			}
		}
	} catch {
		// Proxy HTML or an empty body: keep the HTTP status as the code.
	}
	const retryAfter = Number(response.headers.get("Retry-After"));
	return new ApiError(response.status, code, message, {
		retryAfterSeconds:
			Number.isFinite(retryAfter) && retryAfter > 0 ? retryAfter : null,
	});
}

/**
 * @param {{
 *   baseUrl?: string,
 *   fetchFn?: typeof fetch,
 *   wait?: (milliseconds: number, signal?: AbortSignal) => Promise<void>,
 *   requestIdFactory?: () => string,
 *   maxTurnInProgressWaits?: number,
 * }} [options]
 */
export function createApiClient(options = {}) {
	const baseUrl = parseApiBaseUrl(options.baseUrl) ?? DEFAULT_API_BASE_URL;
	const fetchFn = options.fetchFn ?? globalThis.fetch.bind(globalThis);
	const wait = options.wait ?? defaultWait;
	const requestIdFactory = options.requestIdFactory ?? createRequestId;
	const maxTurnInProgressWaits =
		options.maxTurnInProgressWaits ?? MAX_TURN_IN_PROGRESS_WAITS;

	/**
	 * @param {string} path
	 * @param {RequestInit} [init]
	 * @returns {Promise<Response>}
	 */
	async function request(path, init = {}) {
		/** @type {Headers} */
		const headers = new Headers(init.headers);
		if (!headers.has("X-Request-ID"))
			headers.set("X-Request-ID", requestIdFactory());
		/** @type {Response} */
		let response;
		try {
			response = await fetchFn(`${baseUrl}${path}`, { ...init, headers });
		} catch (error) {
			if (isAbort(error)) throw error;
			throw new ApiError(0, "NETWORK_ERROR", NETWORK_ERROR_MESSAGE);
		}
		if (!response.ok) throw await toApiError(response);
		return response;
	}

	/**
	 * @param {string} path
	 * @param {{ method?: string, body?: unknown, headers?: HeadersInit, signal?: AbortSignal }} [init]
	 * @returns {Promise<unknown>}
	 */
	async function requestJson(path, init = {}) {
		const headers = new Headers(init.headers);
		if (init.body !== undefined)
			headers.set("Content-Type", "application/json");
		headers.set("Accept", "application/json");
		const response = await request(path, {
			method: init.method ?? "GET",
			body: init.body === undefined ? undefined : JSON.stringify(init.body),
			headers,
			signal: init.signal,
		});
		return response.json();
	}

	return {
		baseUrl,

		/**
		 * @param {string | null} [sessionId]
		 * @param {{ signal?: AbortSignal }} [init]
		 * @returns {Promise<SessionSnapshot>}
		 */
		async createSession(sessionId = null, init = {}) {
			const body = sessionId ? { session_id: sessionId } : {};
			return /** @type {SessionSnapshot} */ (
				await requestJson("/api/v1/sessions", {
					method: "POST",
					body,
					signal: init.signal,
				})
			);
		},

		/**
		 * @param {string} sessionId
		 * @param {{ signal?: AbortSignal }} [init]
		 * @returns {Promise<void>}
		 */
		async deleteSession(sessionId, init = {}) {
			await request(`/api/v1/sessions/${encodeURIComponent(sessionId)}`, {
				method: "DELETE",
				signal: init.signal,
			});
		},

		/**
		 * @param {{
		 *   q?: string,
		 *   category?: string,
		 *   voltage?: "127V" | "220V",
		 *   page?: number,
		 *   pageSize?: number,
		 * }} [query]
		 * @param {{ signal?: AbortSignal }} [init]
		 * @returns {Promise<CatalogPage>}
		 */
		async listProducts(query = {}, init = {}) {
			const params = new URLSearchParams();
			if (query.q) params.set("q", query.q);
			if (query.category) params.set("category", query.category);
			if (query.voltage) params.set("voltage", query.voltage);
			if (query.page !== undefined) params.set("page", String(query.page));
			if (query.pageSize !== undefined)
				params.set("page_size", String(query.pageSize));
			const queryString = params.toString();
			const suffix = queryString ? `?${queryString}` : "";
			return /** @type {CatalogPage} */ (
				await requestJson(`/api/v1/products${suffix}`, {
					signal: init.signal,
				})
			);
		},

		/**
		 * @param {string} sku
		 * @param {{ signal?: AbortSignal }} [init]
		 * @returns {Promise<CatalogProduct>}
		 */
		async getProduct(sku, init = {}) {
			return /** @type {CatalogProduct} */ (
				await requestJson(`/api/v1/products/${encodeURIComponent(sku)}`, {
					signal: init.signal,
				})
			);
		},

		/**
		 * @param {{ sessionId: string, clientRequestId: string, message: string, contextFilters?: Record<string, unknown> }} input
		 * @param {{ signal?: AbortSignal }} [init]
		 * @returns {AsyncGenerator<StreamEvent>}
		 */
		async *streamChat(input, init = {}) {
			const body = {
				session_id: input.sessionId,
				client_request_id: input.clientRequestId,
				message: input.message,
				...(input.contextFilters && Object.keys(input.contextFilters).length
					? { context_filters: input.contextFilters }
					: {}),
			};

			/** @type {Response} */
			let response;
			for (let waits = 0; ; waits += 1) {
				try {
					response = await request("/api/v1/chat/stream", {
						method: "POST",
						body: JSON.stringify(body),
						headers: {
							"Content-Type": "application/json",
							Accept: "text/event-stream",
						},
						signal: init.signal,
					});
					break;
				} catch (error) {
					if (
						!(error instanceof ApiError) ||
						error.code !== "TURN_IN_PROGRESS" ||
						waits >= maxTurnInProgressWaits
					) {
						throw error;
					}
					const retryAfter =
						error.retryAfterSeconds ?? DEFAULT_RETRY_AFTER_SECONDS;
					await wait(retryAfter * 1000, init.signal);
				}
			}

			if (!response.body) throw new StreamInterruptedError();
			const reader = response.body.getReader();
			const decoder = new TextDecoder();
			const parser = new SSEParser();
			let receivedDone = false;
			try {
				while (!receivedDone) {
					/** @type {ReadableStreamReadResult<Uint8Array>} */
					let chunk;
					try {
						chunk = await reader.read();
					} catch (error) {
						if (isAbort(error)) throw error;
						throw new StreamInterruptedError();
					}
					const text = chunk.done
						? decoder.decode()
						: decoder.decode(chunk.value, { stream: true });
					const events = chunk.done
						? [...parser.feed(text), ...parser.flush()]
						: parser.feed(text);
					for (const event of events) {
						yield event;
						if (event.event === "done") {
							receivedDone = true;
							break;
						}
					}
					if (chunk.done) break;
				}
			} finally {
				await reader.cancel().catch((error) => {
					if (!isAbort(error))
						console.warn("chat_stream_cancel_failed", error);
				});
			}
			if (!receivedDone) throw new StreamInterruptedError();
		},

		/**
		 * @param {{ session_id: string, message_id: string, rating: "LIKE" | "DISLIKE", reason_category?: string }} feedback
		 * @param {{ signal?: AbortSignal }} [init]
		 * @returns {Promise<{ feedback_id: string, status: "RECORDED", recorded_at: string }>}
		 */
		async postFeedback(feedback, init = {}) {
			return /** @type {{ feedback_id: string, status: "RECORDED", recorded_at: string }} */ (
				await requestJson("/api/v1/feedback", {
					method: "POST",
					body: feedback,
					signal: init.signal,
				})
			);
		},

		/**
		 * @param {CheckoutRequest} checkout
		 * @param {{ signal?: AbortSignal }} [init]
		 * @returns {Promise<Checkout | CheckoutConflict>}
		 */
		async postCheckout(checkout, init = {}) {
			/** @type {Headers} */
			const headers = new Headers({
				"Content-Type": "application/json",
				Accept: "application/json",
				"X-Request-ID": requestIdFactory(),
			});
			/** @type {Response} */
			let response;
			try {
				response = await fetchFn(`${baseUrl}/api/v1/checkout/mock`, {
					method: "POST",
					body: JSON.stringify(checkout),
					headers,
					signal: init.signal,
				});
			} catch (error) {
				if (isAbort(error)) throw error;
				throw new ApiError(0, "NETWORK_ERROR", NETWORK_ERROR_MESSAGE);
			}
			if (response.ok)
				return /** @type {Checkout} */ (await response.json());
			if (response.status === 409) {
				/** @type {unknown} */
				const body = await response
					.clone()
					.json()
					.catch(() => null);
				if (isCheckoutConflict(body)) return body;
			}
			throw await toApiError(response);
		},

		/**
		 * @param {{ signal?: AbortSignal }} [init]
		 * @returns {Promise<{ status: string, components?: Record<string, string>, version?: string }>}
		 */
		async health(init = {}) {
			return /** @type {{ status: string, components?: Record<string, string>, version?: string }} */ (
				await requestJson("/api/v1/health", { signal: init.signal })
			);
		},
	};
}
