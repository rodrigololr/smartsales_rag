/**
 * Application use case for one consultant conversation in the sidebar:
 * session lifecycle, streaming, reconnect/expiry policy, feedback and reset.
 *
 * It depends only on injected adapters (Gateway API, storage repository and
 * settings provider), which keeps it testable without Firefox or a network.
 *
 * @typedef {import("../domain/chat-events.js").StreamEvent} StreamEvent
 * @typedef {import("../domain/chat-state.js").ChatMessage} ChatMessage
 * @typedef {import("../domain/chat-state.js").FeedbackRating} FeedbackRating
 * @typedef {import("../domain/chat-state.js").FeedbackReasonCategory} FeedbackReasonCategory
 * @typedef {import("../infrastructure/gateway-api.js").CatalogProduct} CatalogProduct
 * @typedef {import("../infrastructure/settings.js").ExtensionSettings} ExtensionSettings
 * @typedef {import("./product-context.js").ProductContext} ProductContext
 */

import {
	applyStreamEvent,
	buildFeedbackPayload,
	createAssistantMessage,
	createUserMessage,
	createRestoredAssistantMessage,
	finishWithFailure,
} from "../domain/chat-state.js";
import {
	ApiError,
	StreamInterruptedError,
	createRequestId,
} from "../infrastructure/gateway-api.js";

const MAX_AUTOMATIC_RECONNECTS = 1;
const INTERRUPTED_MESSAGE =
	"A conexão com o consultor caiu antes do fim da resposta. Tente novamente.";
const GENERIC_FAILURE_MESSAGE =
	"Não foi possível concluir a consulta agora. Tente novamente em instantes.";

/**
 * @param {unknown} error
 * @returns {boolean}
 */
const isAbort = (error) =>
	error instanceof Error && error.name === "AbortError";

/**
 * Filters accepted by `ChatStreamRequest.context_filters`. The SKU travels per
 * turn (consultant model), so moving to another product never re-anchors the
 * session implicitly.
 *
 * @param {ExtensionSettings | null | undefined} settings
 * @param {CatalogProduct | null | undefined} product
 * @returns {Record<string, unknown> | undefined}
 */
export function buildContextFilters(settings, product) {
	/** @type {Record<string, unknown>} */
	const filters = {};
	if (product?.sku) filters.current_product_sku = product.sku;
	if (settings?.preferredVoltage)
		filters.preferred_voltage = settings.preferredVoltage;
	if (
		Number.isFinite(settings?.budgetMax) &&
		Number(settings?.budgetMax) > 0
	) {
		filters.budget_max = Math.round(Number(settings?.budgetMax) * 100) / 100;
	}
	return Object.keys(filters).length ? filters : undefined;
}

/**
 * @param {unknown} error
 * @returns {{ errorCode: "LLM_UNAVAILABLE" | "INTERNAL_ERROR", errorFallback: string }}
 */
export function describeTransportFailure(error) {
	if (error instanceof StreamInterruptedError) {
		return {
			errorCode: "LLM_UNAVAILABLE",
			errorFallback: INTERRUPTED_MESSAGE,
		};
	}
	if (error instanceof ApiError) {
		if (error.status === 429) {
			return {
				errorCode: "INTERNAL_ERROR",
				errorFallback:
					"Muitas perguntas em pouco tempo. Aguarde alguns segundos e tente de novo.",
			};
		}
		if (error.code === "SESSION_NOT_FOUND" || error.code === "TURN_EXPIRED") {
			return {
				errorCode: "INTERNAL_ERROR",
				errorFallback:
					"Sua sessão expirou. Envie a pergunta novamente para iniciar outra.",
			};
		}
		if (error.status === 0) {
			return {
				errorCode: "INTERNAL_ERROR",
				errorFallback:
					"Não foi possível conectar ao consultor. Verifique a URL da API nas opções da extensão.",
			};
		}
		return {
			errorCode: "INTERNAL_ERROR",
			errorFallback: error.message || GENERIC_FAILURE_MESSAGE,
		};
	}
	return {
		errorCode: "INTERNAL_ERROR",
		errorFallback: GENERIC_FAILURE_MESSAGE,
	};
}

export class ChatSessionController {
	#api;
	#sessions;
	#getSettings;
	#createId;
	#onChange;
	#logger;
	#maxAutomaticReconnects;
	/** @type {AbortController | null} */
	#abortController = null;
	/** @type {Map<string, string>} assistant local id -> client_request_id already sent */
	#interruptedRequests = new Map();
	/** @type {Map<string, CatalogProduct | null>} */
	#turnProducts = new Map();
	/** @type {{ sessionId: string | null, messages: ChatMessage[], isStreaming: boolean, context: ProductContext | null, notice: string | null, restored: boolean }} */
	#state;

	/**
	 * @param {{
	 *   api: ReturnType<typeof import("../infrastructure/gateway-api.js").createApiClient>,
	 *   sessions: {
	 *     getSessionId: () => Promise<string | null>,
	 *     setSessionId: (sessionId: string) => Promise<void>,
	 *     clearSessionId: () => Promise<void>,
	 *   },
	 *   getSettings: () => Promise<ExtensionSettings> | ExtensionSettings,
	 *   createId?: () => string,
	 *   onChange?: (state: ReturnType<ChatSessionController["getState"]>) => void,
	 *   logger?: Pick<Console, "warn">,
	 *   maxAutomaticReconnects?: number,
	 * }} dependencies
	 */
	constructor({
		api,
		sessions,
		getSettings,
		createId = createRequestId,
		onChange = () => {},
		logger = console,
		maxAutomaticReconnects = MAX_AUTOMATIC_RECONNECTS,
	}) {
		this.#api = api;
		this.#sessions = sessions;
		this.#getSettings = getSettings;
		this.#createId = createId;
		this.#onChange = onChange;
		this.#logger = logger;
		this.#maxAutomaticReconnects = maxAutomaticReconnects;
		this.#state = {
			sessionId: null,
			messages: [],
			isStreaming: false,
			context: null,
			notice: null,
			restored: false,
		};
	}

	getState() {
		return {
			sessionId: this.#state.sessionId,
			messages: this.#state.messages,
			isStreaming: this.#state.isStreaming,
			context: this.#state.context,
			notice: this.#state.notice,
			restored: this.#state.restored,
		};
	}

	#emit() {
		this.#onChange(this.getState());
	}

	/**
	 * Restores the gateway session window when the sidebar is reopened within its
	 * TTL. An expired id makes the gateway create a fresh session (201), which is
	 * persisted silently; the old transcript is not displayed.
	 *
	 * @returns {Promise<ReturnType<ChatSessionController["getState"]>>}
	 */
	async initialize() {
		/** @type {string | null} */
		let stored = null;
		try {
			stored = await this.#sessions.getSessionId();
		} catch (error) {
			this.#logger.warn("session_id_read_failed", error);
			return this.getState();
		}
		if (!stored) return this.getState();

		try {
			const snapshot = await this.#api.createSession(stored);
			this.#state.sessionId = snapshot.session_id;
			await this.#sessions
				.setSessionId(snapshot.session_id)
				.catch((error) => {
					this.#logger.warn("session_id_write_failed", error);
				});
			if (snapshot.restored) {
				this.#state.messages = snapshot.history.map((item) =>
					item.role === "user"
						? createUserMessage(item.id, item.content)
						: createRestoredAssistantMessage(item.id, item.content),
				);
				this.#state.restored = true;
			} else {
				this.#state.notice =
					"Sua conversa anterior expirou; iniciamos uma nova sessão.";
			}
			this.#emit();
		} catch (error) {
			if (error instanceof ApiError && error.status === 404) {
				await this.#sessions.clearSessionId().catch((clearError) => {
					this.#logger.warn("session_id_clear_failed", clearError);
				});
				this.#state.sessionId = null;
			} else {
				// Offline on open should not block the composer: the first send creates
				// a session and surfaces the real transport error if it persists.
				this.#state.sessionId = stored;
				this.#logger.warn("session_restore_failed", error);
			}
			this.#emit();
		}
		return this.getState();
	}

	/** @param {ProductContext | null} context */
	setContext(context) {
		this.#state.context = context;
		this.#emit();
	}

	clearNotice() {
		if (this.#state.notice === null) return;
		this.#state.notice = null;
		this.#emit();
	}

	/**
	 * Updates every card for `sku` with freshly validated SQL values returned by
	 * the mock checkout (R09). Price/stock never come from generated text.
	 *
	 * @param {string} sku
	 * @param {{ price?: number, stock_quantity?: number }} patch
	 */
	patchProduct(sku, patch) {
		let changed = false;
		this.#state.messages = this.#state.messages.map((message) => {
			if (!message.recommendations.some((card) => card.sku === sku))
				return message;
			changed = true;
			return {
				...message,
				recommendations: message.recommendations.map((card) =>
					card.sku === sku ? { ...card, ...patch } : card,
				),
			};
		});
		if (changed) this.#emit();
	}

	/** @param {string} prompt */
	async send(prompt) {
		const question = prompt.trim();
		if (!question || this.#state.isStreaming) return;

		const assistantId = this.#createId();
		const product = this.#state.context?.product ?? null;
		this.#turnProducts.set(assistantId, product);
		this.#state.messages = [
			...this.#state.messages,
			createUserMessage(this.#createId(), question),
			createAssistantMessage(assistantId),
		];
		this.#state.isStreaming = true;
		this.#state.notice = null;
		this.#emit();

		await this.#executeTurn({
			assistantId,
			question,
			product,
			turn: { id: this.#createId() },
		});
	}

	/** @param {string} assistantId */
	async retry(assistantId) {
		if (this.#state.isStreaming) return;
		const index = this.#state.messages.findIndex(
			(message) => message.id === assistantId,
		);
		if (index < 0) return;
		const userMessage = [...this.#state.messages.slice(0, index)]
			.reverse()
			.find((message) => message.role === "user");
		if (!userMessage) return;

		const product =
			this.#turnProducts.get(assistantId) ??
			this.#state.context?.product ??
			null;
		const requestedId =
			this.#interruptedRequests.get(assistantId) ?? this.#createId();
		this.#interruptedRequests.delete(assistantId);
		this.#state.messages = this.#state.messages.map((message) =>
			message.id === assistantId
				? createAssistantMessage(assistantId)
				: message,
		);
		this.#state.isStreaming = true;
		this.#state.notice = null;
		this.#emit();

		await this.#executeTurn({
			assistantId,
			question: userMessage.content,
			product,
			turn: { id: requestedId },
		});
	}

	async reset() {
		this.#abortController?.abort();
		this.#abortController = null;
		const sessionId = this.#state.sessionId;
		this.#state = {
			sessionId: null,
			messages: [],
			isStreaming: false,
			context: this.#state.context,
			notice: null,
			restored: false,
		};
		this.#interruptedRequests.clear();
		this.#turnProducts.clear();
		await this.#sessions.clearSessionId().catch((error) => {
			this.#logger.warn("session_id_clear_failed", error);
		});
		if (sessionId) {
			await this.#api.deleteSession(sessionId).catch((error) => {
				if (!(error instanceof ApiError) || error.status !== 404) {
					this.#logger.warn("session_delete_failed", error);
				}
			});
		}
		this.#emit();
	}

	/**
	 * @param {string} messageId Local message id.
	 * @param {FeedbackRating} rating
	 * @param {FeedbackReasonCategory | null} [reason]
	 */
	async submitFeedback(messageId, rating, reason = null) {
		const message = this.#state.messages.find(
			(candidate) => candidate.id === messageId,
		);
		if (!message?.serverMessageId || !this.#state.sessionId) {
			throw new Error("feedback exige o message_id do servidor");
		}
		const payload = buildFeedbackPayload(
			this.#state.sessionId,
			message.serverMessageId,
			rating,
			reason,
		);
		try {
			await this.#api.postFeedback(payload);
			this.#patchMessage(messageId, {
				feedback: rating,
				feedbackReason: reason ?? null,
			});
		} catch (error) {
			// One rating per assistant message (UC06): 409 means it is already stored.
			if (
				error instanceof ApiError &&
				error.code === "FEEDBACK_ALREADY_RECORDED"
			) {
				this.#patchMessage(messageId, { feedbackAlreadyRecorded: true });
				return;
			}
			throw error;
		}
	}

	destroy() {
		this.#abortController?.abort();
		this.#abortController = null;
	}

	/**
	 * @param {{
	 *   assistantId: string,
	 *   question: string,
	 *   product: CatalogProduct | null,
	 *   turn: { id: string },
	 * }} input
	 */
	async #executeTurn({ assistantId, question, product, turn }) {
		const controller = new AbortController();
		this.#abortController = controller;
		try {
			await this.#runTurn({
				assistantId,
				question,
				product,
				turn,
				signal: controller.signal,
				reconnects: 0,
				sessionRecreated: false,
			});
		} catch (error) {
			if (isAbort(error)) return;
			this.#logger.warn("chat_turn_failed", error);
			if (error instanceof StreamInterruptedError) {
				this.#interruptedRequests.set(assistantId, turn.id);
			}
			if (
				error instanceof ApiError &&
				(error.code === "SESSION_NOT_FOUND" ||
					error.code === "TURN_EXPIRED")
			) {
				this.#state.sessionId = null;
				await this.#sessions.clearSessionId().catch((clearError) => {
					this.#logger.warn("session_id_clear_failed", clearError);
				});
			}
			this.#patchMessage(assistantId, (message) =>
				finishWithFailure(message, describeTransportFailure(error)),
			);
		} finally {
			if (this.#abortController === controller) {
				this.#abortController = null;
				this.#state.isStreaming = false;
				this.#patchMessage(assistantId, (message) =>
					message.isStreaming
						? { ...message, isStreaming: false }
						: message,
				);
				this.#emit();
			}
		}
	}

	/**
	 * @param {{
	 *   assistantId: string,
	 *   question: string,
	 *   product: CatalogProduct | null,
	 *   turn: { id: string },
	 *   signal: AbortSignal,
	 *   reconnects: number,
	 *   sessionRecreated: boolean,
	 * }} input
	 */
	async #runTurn({
		assistantId,
		question,
		product,
		turn,
		signal,
		reconnects,
		sessionRecreated,
	}) {
		await this.#ensureSession(signal);
		const settings = await this.#getSettings();
		const contextFilters = buildContextFilters(settings, product);
		const sessionId = this.#state.sessionId;
		if (!sessionId) throw new Error("sessão indisponível");

		try {
			for await (const event of this.#api.streamChat(
				{
					sessionId,
					clientRequestId: turn.id,
					message: question,
					contextFilters,
				},
				{ signal },
			)) {
				this.#patchMessage(assistantId, (message) =>
					applyStreamEvent(message, event),
				);
			}
			this.#interruptedRequests.delete(assistantId);
		} catch (error) {
			if (isAbort(error)) throw error;
			if (
				error instanceof StreamInterruptedError &&
				reconnects < this.#maxAutomaticReconnects
			) {
				// Same client_request_id, same product: the gateway may replay the
				// completed turn or reject a still-running one with Retry-After.
				this.#interruptedRequests.set(assistantId, turn.id);
				this.#replaceAssistant(assistantId);
				return this.#runTurn({
					assistantId,
					question,
					product,
					turn,
					signal,
					reconnects: reconnects + 1,
					sessionRecreated,
				});
			}
			if (
				error instanceof ApiError &&
				error.code === "SESSION_NOT_FOUND" &&
				!sessionRecreated
			) {
				await this.#recreateSession(signal);
				this.#state.notice =
					"Sua sessão anterior expirou; iniciamos uma nova conversa.";
				this.#replaceAssistant(assistantId);
				turn.id = this.#createId();
				return this.#runTurn({
					assistantId,
					question,
					product,
					turn,
					signal,
					reconnects: 0,
					sessionRecreated: true,
				});
			}
			throw error;
		}
	}

	/** @param {AbortSignal} signal */
	async #ensureSession(signal) {
		if (this.#state.sessionId) return;
		const snapshot = await this.#api.createSession(null, { signal });
		this.#state.sessionId = snapshot.session_id;
		await this.#sessions.setSessionId(snapshot.session_id).catch((error) => {
			this.#logger.warn("session_id_write_failed", error);
		});
	}

	/** @param {AbortSignal} signal */
	async #recreateSession(signal) {
		this.#state.sessionId = null;
		await this.#sessions.clearSessionId().catch((error) => {
			this.#logger.warn("session_id_clear_failed", error);
		});
		await this.#ensureSession(signal);
	}

	/** @param {string} assistantId */
	#replaceAssistant(assistantId) {
		this.#state.messages = this.#state.messages.map((message) =>
			message.id === assistantId
				? createAssistantMessage(assistantId)
				: message,
		);
		this.#emit();
	}

	/**
	 * @param {string} messageId
	 * @param {Partial<ChatMessage> | ((message: ChatMessage) => ChatMessage)} patch
	 */
	#patchMessage(messageId, patch) {
		this.#state.messages = this.#state.messages.map((message) => {
			if (message.id !== messageId) return message;
			return typeof patch === "function"
				? patch(message)
				: { ...message, ...patch };
		});
		this.#emit();
	}
}
