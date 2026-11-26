/**
 * Presentation helpers shared by the sidebar and options page. Pure functions
 * only; no DOM.
 *
 * @typedef {import("../domain/chat-events.js").VoltageType} VoltageType
 * @typedef {import("../domain/chat-events.js").MarketplaceType} MarketplaceType
 * @typedef {import("../domain/chat-events.js").RecommendationType} RecommendationType
 * @typedef {import("../domain/chat-events.js").StreamErrorCode} StreamErrorCode
 * @typedef {import("../domain/chat-state.js").FeedbackReasonCategory} FeedbackReasonCategory
 */

const brl = new Intl.NumberFormat("pt-BR", {
	style: "currency",
	currency: "BRL",
});

/**
 * @param {number} value
 * @returns {string}
 */
export function formatBRL(value) {
	return brl.format(value);
}

/** @type {Record<MarketplaceType, string>} */
const MARKETPLACE_LABEL = {
	AMAZON: "Amazon",
	MERCADO_LIVRE: "Mercado Livre",
	SHOPEE: "Shopee",
	LOJA_OFICIAL: "Loja Oficial",
};

/**
 * @param {MarketplaceType | string} marketplace
 * @returns {string}
 */
export function marketplaceLabel(marketplace) {
	return (
		MARKETPLACE_LABEL[/** @type {MarketplaceType} */ (marketplace)] ??
		"Loja Oficial"
	);
}

/**
 * @param {VoltageType | string} voltage
 * @returns {string}
 */
export function voltageLabel(voltage) {
	if (voltage === "BIVOLT") return "Bivolt";
	if (voltage === "127V" || voltage === "220V") return voltage;
	return "Não se aplica";
}

/**
 * @param {VoltageType | string} voltage
 * @returns {"127v" | "220v" | "bivolt" | "na"}
 */
export function voltageTone(voltage) {
	if (voltage === "220V") return "220v";
	if (voltage === "127V") return "127v";
	if (voltage === "BIVOLT") return "bivolt";
	return "na";
}

/** @type {Record<RecommendationType, string>} */
const RECOMMENDATION_LABEL = {
	PRIMARY: "Recomendado",
	UPSELL: "Upgrade",
	CROSS_SELL: "Combina",
	OPTION: "Opção",
};

/**
 * @param {RecommendationType | string} type
 * @returns {string}
 */
export function recommendationLabel(type) {
	return (
		RECOMMENDATION_LABEL[/** @type {RecommendationType} */ (type)] ?? "Opção"
	);
}

/** @type {Record<FeedbackReasonCategory, string>} */
export const FEEDBACK_REASONS = Object.freeze({
	HALLUCINATION: "Informação imprecisa",
	WRONG_VOLTAGE: "Voltagem/medida incorreta",
	SLOW: "Demorou a responder",
	OTHER: "Outro",
});

/** @type {Record<StreamErrorCode, { title: string, retryable: boolean }>} */
const FALLBACK_INFO = {
	LOW_SIMILARITY_FALLBACK: {
		title: "Informação não encontrada no manual",
		retryable: false,
	},
	GUARDRAIL_BLOCKED: {
		title: "Pergunta fora do escopo do consultor",
		retryable: false,
	},
	LLM_UNAVAILABLE: {
		title: "Consultor indisponível no momento",
		retryable: true,
	},
	INTERNAL_ERROR: {
		title: "Não foi possível concluir a resposta",
		retryable: true,
	},
};

/**
 * @param {StreamErrorCode | null} code
 * @returns {{ title: string, retryable: boolean }}
 */
export function fallbackInfo(code) {
	return FALLBACK_INFO[code ?? "INTERNAL_ERROR"];
}

/**
 * Only http(s) links from the gateway become navigable URLs (blocks
 * javascript:, data:, moz-extension:, ...).
 *
 * @param {string | null | undefined} url
 * @returns {string | null}
 */
export function safeHttpUrl(url) {
	if (!url) return null;
	try {
		const parsed = new URL(url);
		return parsed.protocol === "http:" || parsed.protocol === "https:"
			? parsed.href
			: null;
	} catch {
		return null;
	}
}

/**
 * @param {string} url
 * @returns {string}
 */
export function hostOf(url) {
	try {
		return new URL(url).host;
	} catch {
		return url;
	}
}
