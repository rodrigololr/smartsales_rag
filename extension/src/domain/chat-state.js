/**
 * Pure chat state transitions. The UI renders these values; the controller in
 * `src/application/` owns I/O and orchestration.
 *
 * @typedef {import("./chat-events.js").StreamEvent} StreamEvent
 * @typedef {import("./chat-events.js").ManualCitation} ManualCitation
 * @typedef {import("./chat-events.js").ProductCardData} ProductCardData
 * @typedef {import("./chat-events.js").StreamErrorCode} StreamErrorCode
 * @typedef {"LIKE" | "DISLIKE"} FeedbackRating
 * @typedef {"HALLUCINATION" | "WRONG_VOLTAGE" | "SLOW" | "OTHER"} FeedbackReasonCategory
 *
 * @typedef {Object} ChatMessage
 * @property {string} id
 * @property {"user" | "assistant"} role
 * @property {string} content
 * @property {boolean} isStreaming
 * @property {ManualCitation[]} citations
 * @property {ProductCardData[]} recommendations
 * @property {string | null} serverMessageId
 * @property {FeedbackRating | null} feedback
 * @property {FeedbackReasonCategory | null} feedbackReason
 * @property {boolean} feedbackAlreadyRecorded
 * @property {string | null} errorFallback
 * @property {StreamErrorCode | null} errorCode
 * @property {boolean} wasCorrected
 * @property {number | null} ttftMs
 * @property {boolean} cacheHit
 */

/**
 * @param {string} id
 * @param {string} content
 * @returns {ChatMessage}
 */
export function createUserMessage(id, content) {
	return {
		id,
		role: "user",
		content,
		isStreaming: false,
		citations: [],
		recommendations: [],
		serverMessageId: null,
		feedback: null,
		feedbackReason: null,
		feedbackAlreadyRecorded: false,
		errorFallback: null,
		errorCode: null,
		wasCorrected: false,
		ttftMs: null,
		cacheHit: false,
	};
}

/**
 * @param {string} id
 * @returns {ChatMessage}
 */
export function createAssistantMessage(id) {
	return {
		id,
		role: "assistant",
		content: "",
		isStreaming: true,
		citations: [],
		recommendations: [],
		serverMessageId: null,
		feedback: null,
		feedbackReason: null,
		feedbackAlreadyRecorded: false,
		errorFallback: null,
		errorCode: null,
		wasCorrected: false,
		ttftMs: null,
		cacheHit: false,
	};
}

/**
 * Assistant turn restored from `POST /api/v1/sessions` history. The endpoint
 * exposes only role/content/id, so citations and cards are unavailable.
 *
 * @param {string} id
 * @param {string} content
 * @returns {ChatMessage}
 */
export function createRestoredAssistantMessage(id, content) {
	return {
		...createAssistantMessage(id),
		content,
		isStreaming: false,
		// The session history `id` is the gateway's assistant message id, so a
		// restored answer can still be rated (POST /feedback).
		serverMessageId: id,
	};
}

/**
 * Applies one validated SSE event to an assistant message without mutating the
 * previous value.
 *
 * @param {ChatMessage} message
 * @param {StreamEvent} event
 * @returns {ChatMessage}
 */
export function applyStreamEvent(message, event) {
	switch (event.event) {
		case "metadata":
			return {
				...message,
				serverMessageId: event.data.message_id,
				ttftMs: Number.isFinite(event.data.ttft_ms)
					? event.data.ttft_ms
					: null,
				cacheHit: Boolean(event.data.cache_hit),
			};
		case "token":
			return { ...message, content: message.content + event.data.delta };
		case "correction":
			return { ...message, content: event.data.content, wasCorrected: true };
		case "citations":
			return { ...message, citations: event.data.citations };
		case "recommendations":
			return { ...message, recommendations: event.data.products };
		case "error":
			// Contract: discard every partial text/citation/card. Later cards in this
			// same turn are new ones, emitted after the safe fallback.
			return {
				...message,
				content: "",
				citations: [],
				recommendations: [],
				wasCorrected: false,
				errorFallback: event.data.fallback_message,
				errorCode: event.data.code,
			};
		case "done":
			return { ...message, isStreaming: false };
	}
}

/**
 * Terminal transport/protocol failure: partial content never survives.
 *
 * @param {ChatMessage} message
 * @param {{ errorCode: StreamErrorCode, errorFallback: string }} failure
 * @returns {ChatMessage}
 */
export function finishWithFailure(message, failure) {
	return {
		...message,
		content: "",
		citations: [],
		recommendations: [],
		isStreaming: false,
		wasCorrected: false,
		errorCode: failure.errorCode,
		errorFallback: failure.errorFallback,
	};
}

/**
 * @param {ChatMessage} message
 * @returns {boolean}
 */
export const canRate = (message) =>
	message.role === "assistant" &&
	!message.isStreaming &&
	Boolean(message.serverMessageId) &&
	Boolean(message.content) &&
	!message.errorFallback;

/**
 * @param {ChatMessage} message
 * @returns {boolean}
 */
export const canBuyFrom = (message) =>
	message.role === "assistant" &&
	!message.isStreaming &&
	Boolean(message.serverMessageId) &&
	message.recommendations.length > 0;

/**
 * `POST /api/v1/feedback` requires `reason_category` for DISLIKE.
 *
 * @param {string} sessionId
 * @param {string} serverMessageId
 * @param {FeedbackRating} rating
 * @param {FeedbackReasonCategory | null} [reason]
 * @returns {{ session_id: string, message_id: string, rating: FeedbackRating, reason_category?: FeedbackReasonCategory }}
 */
export function buildFeedbackPayload(
	sessionId,
	serverMessageId,
	rating,
	reason = null,
) {
	if (!sessionId || !serverMessageId) {
		throw new Error("feedback exige session_id e message_id do servidor");
	}
	if (rating === "DISLIKE" && !reason) {
		throw new Error("DISLIKE exige reason_category");
	}
	return rating === "DISLIKE" && reason
		? {
				session_id: sessionId,
				message_id: serverMessageId,
				rating,
				reason_category: reason,
			}
		: { session_id: sessionId, message_id: serverMessageId, rating: "LIKE" };
}
