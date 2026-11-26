/**
 * Sidebar presentation layer. All network, session and retry policy lives in
 * `ChatSessionController`; this file only translates state into DOM and user
 * gestures into controller calls.
 */

import { ChatSessionController } from "../src/application/chat-session.js";
import { resolveProductContext } from "../src/application/product-context.js";
import { canBuyFrom, canRate } from "../src/domain/chat-state.js";
import {
	ApiError,
	createApiClient,
} from "../src/infrastructure/gateway-api.js";
import {
	DEFAULT_SETTINGS,
	SETTINGS_STORAGE_KEY,
	createSettingsRepository,
	normalizeDetectedProduct,
} from "../src/infrastructure/settings.js";
import {
	FEEDBACK_REASONS,
	fallbackInfo,
	formatBRL,
	hostOf,
	marketplaceLabel,
	recommendationLabel,
	safeHttpUrl,
	voltageLabel,
	voltageTone,
} from "../src/ui/format.js";
import { createIcon } from "../src/ui/icons.js";

const CATALOG_SUGGESTIONS = [
	"Quero um PC para jogar Roblox até R$ 4.000",
	"Qual notebook gamer funciona em 127V?",
	"Quero um monitor para jogos",
	"Qual webcam serve para live na Twitch?",
	"Um sofá de 3 lugares cabe em 2 metros?",
];

const HEALTH_INTERVAL_MS = 60_000;
const MAX_AUTOMATIC_RECONNECTS = 1;
// Set by background.js when the sidebar had to be opened as a regular tab.
const IS_STANDALONE =
	new URLSearchParams(location.search).get("source") === "standalone";

const elements = {
	settingsButton: document.getElementById("settings-button"),
	resetButton: document.getElementById("reset-button"),
	connectionBanner: document.getElementById("connection-banner"),
	connectionText: document.getElementById("connection-text"),
	connectionAction: document.getElementById("connection-action"),
	noticeBanner: document.getElementById("notice-banner"),
	noticeText: document.getElementById("notice-text"),
	noticeDismiss: document.getElementById("notice-dismiss"),
	contextBar: document.getElementById("context-bar"),
	chatLog: document.getElementById("chat-log"),
	messages: document.getElementById("messages"),
	chatAnnouncer: document.getElementById("chat-announcer"),
	composer: document.getElementById("composer"),
	prompt: document.getElementById("prompt"),
	sendButton: document.getElementById("send-button"),
	counter: document.getElementById("counter"),
	connectionDot: document.getElementById("connection-dot"),
	checkoutDialog: document.getElementById("checkout-dialog"),
	checkoutClose: document.getElementById("checkout-close"),
	checkoutBody: document.getElementById("checkout-body"),
	checkoutCancel: document.getElementById("checkout-cancel"),
	checkoutConfirm: document.getElementById("checkout-confirm"),
};

const repository = createSettingsRepository({
	localArea: browser.storage.local,
	sessionArea: browser.storage.session ?? browser.storage.local,
});

/** @type {import("../src/infrastructure/settings.js").ExtensionSettings} */
let settings = { ...DEFAULT_SETTINGS };
let client = createApiClient({ baseUrl: settings.apiBaseUrl });

/**
 * Stable proxy: the settings page may change the API origin while this sidebar
 * is open; controllers keep the same adapter object and the next call uses the
 * new client.
 */
const api = {
	createSession: (...args) => client.createSession(...args),
	deleteSession: (...args) => client.deleteSession(...args),
	listProducts: (...args) => client.listProducts(...args),
	getProduct: (...args) => client.getProduct(...args),
	streamChat: (...args) => client.streamChat(...args),
	postFeedback: (...args) => client.postFeedback(...args),
	postCheckout: (...args) => client.postCheckout(...args),
	health: (...args) => client.health(...args),
};

let controller;
let chatState = {
	sessionId: null,
	messages: [],
	isStreaming: false,
	context: null,
	notice: null,
	restored: false,
};
let activeTabId = null;
let contextState = {
	phase: "idle",
	detection: null,
	product: null,
	error: null,
};
let currentDetectionSignature = "";
let ignoredDetectionSignature = null;
let contextRequestCounter = 0;
let expandedCitations = new Set();
let feedbackUi = new Map();
let checkoutState = null;
let healthState = "unknown";
let announcedMessageId = null;
let healthTimer = 0;
let lastMessageCount = 0;

function installIcons() {
	elements.settingsButton.append(createIcon("gear", { size: 17 }));
	elements.resetButton.append(createIcon("reset", { size: 17 }));
	elements.noticeDismiss.append(createIcon("close", { size: 13 }));
	elements.sendButton.append(createIcon("send", { size: 15 }));
	elements.checkoutClose.append(createIcon("close", { size: 16 }));
}

/**
 * @param {string} tag
 * @param {string} [className]
 * @param {string} [text]
 * @returns {HTMLElement}
 */
function el(tag, className, text) {
	const node = document.createElement(tag);
	if (className) node.className = className;
	if (text !== undefined) node.textContent = text;
	return node;
}

function isReduceMotion() {
	return (
		window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false
	);
}

function isNearBottom() {
	return (
		elements.chatLog.scrollHeight -
			elements.chatLog.scrollTop -
			elements.chatLog.clientHeight <
		100
	);
}

function scrollToBottom(force = false) {
	if (!force && !isNearBottom()) return;
	window.requestAnimationFrame(() => {
		elements.chatLog.scrollTo({
			top: elements.chatLog.scrollHeight,
			behavior: isReduceMotion() ? "auto" : "smooth",
		});
	});
}

function autoResizePrompt() {
	elements.prompt.style.height = "auto";
	elements.prompt.style.height = `${Math.min(elements.prompt.scrollHeight, 120)}px`;
}

function renderComposer() {
	const prompt = elements.prompt.value.trim();
	elements.sendButton.disabled =
		!prompt || chatState.isStreaming || !controller;
	elements.counter.textContent =
		elements.prompt.value.length >= 850
			? `${elements.prompt.value.length}/1000`
			: "";
	elements.prompt.placeholder = chatState.context?.product
		? "Pergunte sobre este produto"
		: "Pergunte sobre o produto ou o catálogo";
	elements.chatLog.setAttribute("aria-busy", String(chatState.isStreaming));
}

function renderNotice() {
	elements.noticeBanner.hidden = !chatState.notice;
	elements.noticeText.textContent = chatState.notice ?? "";
}

function renderConnection() {
	const host = hostOf(settings.apiBaseUrl);
	elements.connectionBanner.hidden =
		healthState === "ok" || healthState === "unknown";
	elements.connectionBanner.classList.toggle(
		"banner--warning",
		healthState === "degraded",
	);
	elements.connectionBanner.classList.toggle(
		"banner--error",
		healthState === "unreachable",
	);
	if (healthState === "degraded") {
		elements.connectionText.textContent = `O serviço em ${host} está degradado; algumas respostas podem falhar.`;
	} else if (healthState === "unreachable") {
		elements.connectionText.textContent = `Não foi possível falar com o consultor em ${host}.`;
	} else {
		elements.connectionText.textContent = "";
	}
	elements.connectionAction.hidden = healthState !== "unreachable";
	elements.connectionDot.dataset.state = healthState;
	elements.connectionDot.title =
		healthState === "ok"
			? "Conectado ao gateway"
			: healthState === "degraded"
				? "Gateway degradado"
				: healthState === "unreachable"
					? "Gateway inacessível"
					: "Verificando conexão";
}

async function checkHealth() {
	try {
		const response = await api.health();
		healthState = response.status === "ok" ? "ok" : "degraded";
	} catch {
		healthState = "unreachable";
	}
	renderConnection();
}

function openOptions() {
	const optionsUrl = browser.runtime.getURL("options/options.html");
	Promise.resolve()
		.then(() => browser.runtime.openOptionsPage())
		.catch(() => {
			void browser.tabs.create({ url: optionsUrl });
		});
}

function sendQuestion(text) {
	if (!controller || chatState.isStreaming || !text.trim()) return;
	elements.prompt.value = "";
	autoResizePrompt();
	renderComposer();
	void controller.send(text);
	elements.prompt.focus();
}

/* ------------------------------------------------------------------------- */
/* Messages                                                                   */
/* ------------------------------------------------------------------------- */

function renderMessages() {
	const forceScroll = chatState.messages.length > lastMessageCount;
	lastMessageCount = chatState.messages.length;
	const nearBottom = isNearBottom();
	const fragment = document.createDocumentFragment();

	if (chatState.messages.length === 0) {
		fragment.append(renderWelcome());
	} else {
		for (const message of chatState.messages) {
			fragment.append(
				message.role === "user"
					? renderUserMessage(message)
					: renderAssistantMessage(message),
			);
		}
	}

	elements.messages.replaceChildren(fragment);
	renderComposer();
	updateAnnouncement();
	if (forceScroll || nearBottom) scrollToBottom(true);
}

function renderWelcome() {
	const container = el("section", "welcome");
	const intro = el("div", "welcome__intro");
	const spark = createIcon("spark", { size: 16, className: "welcome__spark" });
	const text = el("div");
	const product = chatState.context?.product ?? null;
	const detection = chatState.context?.detection ?? null;
	if (product) {
		text.append(
			el("strong", undefined, "Olá! Tire suas dúvidas sobre este produto."),
		);
		text.append(
			document.createTextNode(
				"Respondo sobre especificações, uso e cuidados com base no manual oficial e na ficha técnica, citando a página da fonte.",
			),
		);
	} else if (detection && !product) {
		text.append(
			el("strong", undefined, "Produto da página fora do catálogo."),
		);
		text.append(
			document.createTextNode(
				"Posso ajudar com o catálogo SmartSales, comparar modelos em estoque e consultar os manuais.",
			),
		);
	} else {
		text.append(
			el("strong", undefined, "Olá! Posso ajudar a escolher um produto."),
		);
		text.append(
			document.createTextNode(
				"Busco opções em estoque, comparo especificações dos manuais e cito a fonte de cada resposta.",
			),
		);
	}
	intro.append(spark, text);
	container.append(intro);
	container.append(el("h3", "welcome__title", "Sugestões para começar"));

	const suggestions = el("div", "suggestions");
	for (const suggestion of suggestionsFor(product)) {
		const button = el("button", "quick-suggestion", suggestion);
		button.type = "button";
		button.addEventListener("click", () => sendQuestion(suggestion));
		suggestions.append(button);
	}
	container.append(suggestions);
	return container;
}

/**
 * @param {import("../src/infrastructure/gateway-api.js").CatalogProduct | null} product
 * @returns {string[]}
 */
function suggestionsFor(product) {
	if (!product) return CATALOG_SUGGESTIONS;
	const first =
		product.voltage === "N/A"
			? "Quais são as principais especificações deste modelo?"
			: `Qual é a voltagem oficial deste modelo (${voltageLabel(product.voltage)})?`;
	if (product.subcategory === "Cafeteiras") {
		return [
			first,
			"Qual é a pressão da bomba?",
			"Como faço a descalcificação?",
		];
	}
	if (
		product.subcategory === "Fritadeiras Elétricas" &&
		product.capacity_liters
	) {
		return [
			first,
			`A capacidade de ${product.capacity_liters}L atende quantas pessoas?`,
			"Quais materiais de forma e assadeira posso utilizar?",
		];
	}
	if (product.category === "Computadores") {
		return [
			"Consigo jogar GTA RP neste computador?",
			"Funciona em 127V?",
			first,
		];
	}
	if (product.subcategory === "Webcams") {
		return ["Consigo fazer live na Twitch com a melhor qualidade?", first];
	}
	if (product.category === "Monitores") {
		return ["Qual é a taxa de atualização?", first];
	}
	return [
		first,
		"Como devo fazer a limpeza?",
		"Quais são os cuidados de uso?",
	];
}

function renderUserMessage(message) {
	const wrapper = el("div", "message--user");
	wrapper.append(el("div", "user-bubble", message.content));
	return wrapper;
}

function renderAssistantMessage(message) {
	const container = el("article", "assistant");
	const head = el("header", "assistant__head");
	const name = el("span", "assistant__name");
	name.append(
		createIcon("chat", { size: 12 }),
		document.createTextNode("Consultor IA"),
	);
	head.append(name);
	if (message.cacheHit) {
		const cache = el("span", "chip chip--cache");
		cache.append(
			createIcon("bolt", { size: 9 }),
			document.createTextNode("Cache"),
		);
		head.append(cache);
	}
	if (message.wasCorrected)
		head.append(el("span", "chip", "Resposta corrigida"));
	if (typeof message.ttftMs === "number") {
		head.append(el("span", "assistant__meta", `TTFT ${message.ttftMs} ms`));
	}
	container.append(head);

	const isThinking =
		message.isStreaming && !message.content && !message.errorFallback;
	if (isThinking) {
		const thinking = el("div", "thinking");
		const dots = el("span", "dots");
		dots.append(el("span"), el("span"), el("span"));
		thinking.append(
			dots,
			document.createTextNode("Consultando manuais e catálogo..."),
		);
		container.append(thinking);
	}

	if (message.content) {
		const bubble = el("div", "bubble", message.content);
		if (message.isStreaming) bubble.append(el("span", "caret"));
		container.append(bubble);
	}

	if (message.errorFallback) {
		container.append(renderFallback(message));
	}

	if (message.citations.length) {
		container.append(renderCitations(message));
	}

	if (message.recommendations.length) {
		container.append(renderRecommendations(message));
	}

	if (canRate(message)) {
		container.append(renderFeedback(message));
	}

	return container;
}

function renderFallback(message) {
	const info = fallbackInfo(message.errorCode);
	const tone =
		message.errorCode === "GUARDRAIL_BLOCKED"
			? "warning"
			: message.errorCode === "LOW_SIMILARITY_FALLBACK"
				? "info"
				: "error";
	const box = el("div", "fallback");
	box.dataset.tone = tone;
	const title = el("span", "fallback__title");
	title.append(
		createIcon(
			tone === "info" ? "book" : tone === "warning" ? "warning" : "warning",
			{
				size: 13,
			},
		),
		document.createTextNode(info.title),
	);
	box.append(title, el("p", "fallback__message", message.errorFallback ?? ""));
	if (info.retryable && !message.isStreaming) {
		const retry = el("button", "retry-button");
		retry.type = "button";
		retry.append(
			createIcon("reset", { size: 11 }),
			document.createTextNode("Tentar novamente"),
		);
		retry.addEventListener("click", () => {
			void controller?.retry(message.id);
		});
		box.append(retry);
	}
	return box;
}

function renderCitations(message) {
	const list = el("section", "citations");
	list.setAttribute("aria-label", "Fontes consultadas no manual");
	const messageId = message.id;
	message.citations.forEach((citation, index) => {
		const key = `${messageId}:${index}`;
		const panelId = `citation-${messageId}-${index}`;
		const button = el("button", "citation");
		button.type = "button";
		button.setAttribute("aria-expanded", String(expandedCitations.has(key)));
		button.setAttribute("aria-controls", panelId);
		button.append(createIcon("book", { size: 12 }));
		button.append(
			el(
				"span",
				"citation__title",
				`${citation.manual_title} — p. ${citation.page_number}`,
			),
		);
		button.append(el("span", "citation__chevron", "▾"));

		const panel = el("div", "citation__panel");
		panel.id = panelId;
		panel.hidden = !expandedCitations.has(key);
		if (citation.section_title) {
			panel.append(
				el("p", "citation__section", `Seção: ${citation.section_title}`),
			);
		}
		panel.append(
			el("blockquote", "citation__excerpt", `“${citation.excerpt}”`),
		);
		panel.append(
			el(
				"p",
				"citation__foot",
				`Trecho literal do manual, página ${citation.page_number} (similaridade ${Math.round(
					citation.similarity_score * 100,
				)}%).`,
			),
		);

		button.addEventListener("click", () => {
			const isOpen = !panel.hidden;
			panel.hidden = isOpen;
			button.setAttribute("aria-expanded", String(!isOpen));
			if (isOpen) expandedCitations.delete(key);
			else expandedCitations.add(key);
		});

		list.append(button, panel);
	});
	return list;
}

function renderRecommendations(message) {
	const container = el("section", "recommendations");
	container.setAttribute("aria-label", "Produtos recomendados");
	for (const card of message.recommendations) {
		container.append(renderProductCard(card, message));
	}
	return container;
}

function createThumb(imageUrl, name) {
	const thumb = el("div", "thumb");
	const safeUrl = safeHttpUrl(imageUrl);
	if (safeUrl) {
		const image = document.createElement("img");
		image.src = safeUrl;
		image.alt = "";
		image.loading = "lazy";
		image.referrerPolicy = "no-referrer";
		image.addEventListener("error", () => {
			image.remove();
			thumb.textContent = (name || "?").trim().slice(0, 1).toUpperCase();
		});
		thumb.append(image);
	} else {
		thumb.textContent = (name || "?").trim().slice(0, 1).toUpperCase();
	}
	return thumb;
}

function renderProductCard(card, message) {
	const article = el("article", "rec-card");
	article.dataset.type = card.recommendation_type;
	article.dataset.sku = card.sku;

	const top = el("div", "rec-card__top");
	top.append(
		el(
			"span",
			"rec-badge",
			card.badge_label || recommendationLabel(card.recommendation_type),
		),
	);
	if (card.voltage !== "N/A") {
		const voltage = el("span", "voltage-badge", voltageLabel(card.voltage));
		voltage.dataset.tone = voltageTone(card.voltage);
		top.append(voltage);
	}
	article.append(top);

	const product = el("div", "rec-card__product");
	product.append(createThumb(card.image_url, card.name));
	const text = el("div", "rec-card__text");
	text.append(
		el("p", "rec-card__name", card.name),
		el("p", "rec-card__sku", card.sku),
	);
	product.append(text);
	article.append(product);

	if (card.justification) {
		article.append(el("p", "rec-card__justification", card.justification));
	}
	const specs = [];
	if (typeof card.capacity_liters === "number")
		specs.push(`${card.capacity_liters} L`);
	if (typeof card.power_watts === "number")
		specs.push(`${card.power_watts} W`);
	if (specs.length)
		article.append(el("p", "rec-card__specs", specs.join(" · ")));

	const priceRow = el("div", "rec-card__price-row");
	priceRow.append(el("span", "rec-card__price", formatBRL(card.price)));
	const inStock = card.stock_quantity > 0;
	priceRow.append(
		el(
			"span",
			inStock ? "rec-card__stock" : "rec-card__stock rec-card__stock--out",
			inStock ? `Em estoque (${card.stock_quantity})` : "Esgotado",
		),
	);
	article.append(priceRow);

	const canBuy = canBuyFrom(message) && inStock;
	const buy = el("button", "buy-button");
	buy.type = "button";
	buy.disabled = !canBuy;
	buy.append(
		createIcon("cart", { size: 12 }),
		document.createTextNode(
			inStock
				? `Comprar na ${marketplaceLabel(card.marketplace)}`
				: "Indisponível",
		),
	);
	if (!canBuy) {
		buy.title =
			message.isStreaming || !message.serverMessageId
				? "Aguarde a resposta terminar para comprar."
				: "Produto esgotado no catálogo.";
	}
	buy.addEventListener("click", () => openCheckout(card, message));
	article.append(buy);

	return article;
}

/* ------------------------------------------------------------------------- */
/* Feedback                                                                   */
/* ------------------------------------------------------------------------- */

function feedbackStateFor(messageId) {
	if (!feedbackUi.has(messageId)) {
		feedbackUi.set(messageId, {
			showReasons: false,
			pending: false,
			error: null,
			failed: null,
		});
	}
	return feedbackUi.get(messageId);
}

function describeFeedbackError(error) {
	const byStatus = {
		404: "Não encontramos esta resposta no servidor para registrar a avaliação.",
		410: "Sua sessão expirou. Faça a pergunta de novo para avaliar.",
		422: "A avaliação não pôde ser validada pelo servidor.",
		429: "Muitas avaliações em pouco tempo. Aguarde alguns segundos.",
	};
	return (
		(error instanceof ApiError && byStatus[error.status]) ||
		"O serviço de avaliações está indisponível agora. Tente de novo."
	);
}

function renderFeedback(message) {
	const container = el("div", "feedback");
	if (message.feedbackAlreadyRecorded) {
		const status = el("p", "feedback__status");
		status.append(
			createIcon("check", { size: 12 }),
			document.createTextNode("Esta resposta já foi avaliada."),
		);
		return status;
	}
	if (message.feedback) {
		const status = el("p", "feedback__status");
		status.append(
			createIcon("check", { size: 12 }),
			document.createTextNode("Obrigado pelo feedback!"),
		);
		return status;
	}

	const ui = feedbackStateFor(message.id);
	container.append(el("span", undefined, "Esta resposta foi útil?"));
	const like = el("button", "feedback-button feedback-button--like");
	like.type = "button";
	like.disabled = ui.pending;
	like.append(
		createIcon("thumbs-up", { size: 12 }),
		document.createTextNode("Útil"),
	);
	like.addEventListener(
		"click",
		() => void submitFeedback(message.id, "LIKE", null),
	);
	container.append(like);

	const dislike = el("button", "feedback-button feedback-button--dislike");
	dislike.type = "button";
	dislike.disabled = ui.pending;
	dislike.setAttribute("aria-expanded", String(ui.showReasons));
	dislike.append(
		createIcon("thumbs-down", { size: 12 }),
		document.createTextNode("Não útil"),
	);
	dislike.addEventListener("click", () => {
		ui.showReasons = !ui.showReasons;
		renderMessages();
	});
	container.append(dislike);

	if (ui.showReasons) {
		const reasons = el("div", "feedback__reasons");
		reasons.setAttribute("role", "group");
		reasons.setAttribute("aria-label", "Motivo da avaliação negativa");
		for (const [value, label] of Object.entries(FEEDBACK_REASONS)) {
			const reason = el("button", "reason-chip", label);
			reason.type = "button";
			reason.disabled = ui.pending;
			reason.addEventListener(
				"click",
				() =>
					void submitFeedback(
						message.id,
						"DISLIKE",
						/** @type {any} */ (value),
					),
			);
			reasons.append(reason);
		}
		container.append(reasons);
	}

	if (ui.error && ui.failed) {
		const error = el("div", "feedback__error");
		error.append(document.createTextNode(ui.error));
		const retry = el("button", "retry-button");
		retry.type = "button";
		retry.disabled = ui.pending;
		retry.append(
			createIcon("reset", { size: 10 }),
			document.createTextNode("Tentar enviar de novo"),
		);
		retry.addEventListener(
			"click",
			() =>
				void submitFeedback(message.id, ui.failed.rating, ui.failed.reason),
		);
		error.append(retry);
		container.append(error);
	}

	return container;
}

async function submitFeedback(messageId, rating, reason) {
	const ui = feedbackStateFor(messageId);
	if (ui.pending) return;
	ui.pending = true;
	ui.error = null;
	ui.failed = { rating, reason };
	renderMessages();
	try {
		await controller.submitFeedback(messageId, rating, reason);
		ui.showReasons = false;
		ui.failed = null;
	} catch (error) {
		ui.error = describeFeedbackError(error);
	} finally {
		ui.pending = false;
		renderMessages();
	}
}

/* ------------------------------------------------------------------------- */
/* Product context                                                            */
/* ------------------------------------------------------------------------- */

function contextSignature(detection) {
	return detection
		? `${detection.url}|${detection.sku ?? ""}|${detection.name ?? ""}`
		: "none";
}

async function applyDetection(rawDetection) {
	const detection = normalizeDetectedProduct(rawDetection);
	const signature = contextSignature(detection);
	if (signature === currentDetectionSignature) return;
	currentDetectionSignature = signature;

	if (!detection) {
		contextRequestCounter += 1;
		ignoredDetectionSignature = null;
		contextState = {
			phase: "idle",
			detection: null,
			product: null,
			error: null,
		};
		controller?.setContext(null);
		renderContextBar();
		return;
	}
	if (ignoredDetectionSignature === signature) return;

	const requestId = ++contextRequestCounter;
	contextState = { phase: "loading", detection, product: null, error: null };
	renderContextBar();
	try {
		const resolved = await resolveProductContext({ api, detection });
		if (requestId !== contextRequestCounter) return;
		contextState = {
			phase: resolved.product ? "ready" : "unmatched",
			detection,
			product: resolved.product,
			error: null,
		};
		controller?.setContext(resolved);
		renderContextBar();
	} catch (error) {
		if (requestId !== contextRequestCounter) return;
		contextState = { phase: "error", detection, product: null, error };
		controller?.setContext({ product: null, detection, resolvedBy: null });
		renderContextBar();
	}
}

async function refreshContextFromActiveTab() {
	try {
		const [tab] = await browser.tabs.query({
			active: true,
			currentWindow: true,
		});
		activeTabId = tab?.id ?? null;
		if (tab?.id === undefined) return;
		const detection = await browser.tabs.sendMessage(tab.id, {
			type: "smartsales:detect-product",
		});
		await applyDetection(detection);
	} catch {
		// No content script on this page (about:, add-ons, PDF viewer...).
		await applyDetection(null);
	}
}

async function initializeContext() {
	try {
		const [tab] = await browser.tabs.query({
			active: true,
			currentWindow: true,
		});
		activeTabId = tab?.id ?? null;
	} catch {
		activeTabId = null;
	}
	try {
		const pending = await repository.takePendingProduct();
		// A pending context from another tab is ignored unless this page is the
		// standalone-tab fallback (there is no active product tab to query then).
		if (
			pending &&
			(IS_STANDALONE ||
				pending.tabId === null ||
				pending.tabId === activeTabId)
		) {
			await applyDetection(pending.product);
			return;
		}
	} catch (error) {
		console.warn("pending_product_read_failed", error);
	}
	await refreshContextFromActiveTab();
}

function retryContextDetection() {
	if (!contextState.detection) return;
	currentDetectionSignature = "";
	void applyDetection(contextState.detection);
}

function renderContextBar() {
	const state = contextState;
	const visible =
		state.phase !== "idle" &&
		state.phase !== "none" &&
		Boolean(state.detection || state.phase === "loading");
	elements.contextBar.hidden = !visible;
	elements.contextBar.replaceChildren();
	if (!visible) return;

	elements.contextBar.classList.toggle(
		"context--warning",
		state.phase === "unmatched" || state.phase === "error",
	);
	elements.contextBar.classList.toggle(
		"context--error",
		state.phase === "error",
	);

	const icon = el("span", "context__icon");
	icon.append(
		createIcon(state.phase === "ready" ? "chat" : "info", { size: 14 }),
	);
	const body = el("div", "context__body");
	const remove = el("button", "icon-button context__remove");
	remove.type = "button";
	remove.title = "Remover contexto do produto";
	remove.setAttribute("aria-label", "Remover contexto do produto");
	remove.append(createIcon("close", { size: 13 }));
	remove.addEventListener("click", () => {
		ignoredDetectionSignature = currentDetectionSignature;
		contextRequestCounter += 1;
		contextState = {
			phase: "idle",
			detection: null,
			product: null,
			error: null,
		};
		controller?.setContext(null);
		renderContextBar();
		renderMessages();
	});

	if (state.phase === "loading") {
		body.append(
			el(
				"span",
				"context__title",
				"Identificando o produto desta página...",
			),
		);
		body.append(
			el(
				"span",
				"context__meta",
				`Consultando ${hostOf(settings.apiBaseUrl)}`,
			),
		);
		elements.contextBar.append(icon, body, remove);
		return;
	}

	if (state.phase === "ready" && state.product) {
		body.append(el("span", "context__title", state.product.name));
		const meta = el("span", "context__meta");
		meta.append(el("span", "context__sku", state.product.sku));
		if (state.product.voltage !== "N/A") {
			const voltage = el(
				"span",
				"voltage-badge",
				voltageLabel(state.product.voltage),
			);
			voltage.dataset.tone = voltageTone(state.product.voltage);
			meta.append(voltage);
		}
		body.append(meta);
		elements.contextBar.append(icon, body, remove);
		return;
	}

	if (state.phase === "unmatched" && state.detection) {
		body.append(
			el(
				"span",
				"context__title",
				state.detection.name
					? `Página: ${state.detection.name}`
					: "Produto da página não identificado",
			),
		);
		body.append(
			el(
				"span",
				"context__meta",
				"Fora do catálogo SmartSales — conversando em modo catálogo.",
			),
		);
		elements.contextBar.append(icon, body, remove);
		return;
	}

	body.append(
		el(
			"span",
			"context__title",
			"Não foi possível verificar o produto da página.",
		),
	);
	const retry = el("button", "link-button", "Tentar de novo");
	retry.type = "button";
	retry.addEventListener("click", retryContextDetection);
	const meta = el("span", "context__meta");
	meta.append(retry);
	body.append(meta);
	elements.contextBar.append(icon, body, remove);
}

/* ------------------------------------------------------------------------- */
/* Checkout                                                                   */
/* ------------------------------------------------------------------------- */

function describeCheckoutError(error) {
	const byStatus = {
		404: "Este item não está mais disponível no catálogo. Peça uma alternativa ao consultor.",
		410: "Sua sessão expirou. Faça a pergunta de novo para receber recomendações atualizadas.",
		422: "O pedido não pôde ser validado pelo servidor.",
		429: "Muitas tentativas seguidas. Aguarde alguns segundos.",
	};
	if (error instanceof ApiError) {
		if (error.status === 0) {
			return "Não foi possível falar com o checkout. Verifique a conexão com o gateway.";
		}
		return byStatus[error.status] ?? error.message;
	}
	return "O checkout está indisponível no momento. Tente novamente em instantes.";
}

function openCheckout(card, message) {
	if (!message.serverMessageId || card.stock_quantity <= 0) return;
	checkoutState = {
		card,
		message,
		phase: "confirm",
		acceptedPrice: null,
		result: null,
		error: null,
		pending: false,
	};
	renderCheckout();
	if (!elements.checkoutDialog.open) elements.checkoutDialog.showModal();
}

function closeCheckout() {
	if (checkoutState?.pending) return;
	elements.checkoutDialog.close();
}

function renderCheckout() {
	const state = checkoutState;
	elements.checkoutBody.replaceChildren();
	elements.checkoutConfirm.classList.remove("button--danger");
	if (!state) return;

	const product = el("div", "dialog-product");
	product.append(createThumb(state.card.image_url, state.card.name));
	const productText = el("div");
	productText.append(el("p", "dialog-product__name", state.card.name));
	productText.append(el("p", "dialog-product__sku", state.card.sku));
	product.append(productText);
	elements.checkoutBody.append(product);

	const summary = el("dl", "summary");
	const addRow = (label, value, className) => {
		const row = el(
			"div",
			className ? `summary__row ${className}` : "summary__row",
		);
		row.append(el("dt", undefined, label), el("dd", undefined, value));
		summary.append(row);
	};

	if (state.phase === "confirm" || state.phase === "pending") {
		addRow(
			"Preço exibido",
			formatBRL(state.acceptedPrice ?? state.card.price),
		);
		addRow("Quantidade", "1 unidade");
		addRow("Estoque consultado", `${state.card.stock_quantity} un.`);
		addRow("Marketplace", marketplaceLabel(state.card.marketplace));
		elements.checkoutBody.append(summary);
		elements.checkoutBody.append(
			el(
				"p",
				"dialog-note",
				"Ao continuar, o preço e o estoque serão revalidados no PostgreSQL. Depois você será levado ao anúncio oficial.",
			),
		);
		if (state.phase === "pending") {
			const status = el("div", "dialog-status dialog-status--confirmed");
			const spinner = el("span", "spinner");
			spinner.append(el("span"), el("span"), el("span"));
			status.append(
				spinner,
				document.createTextNode("Validando preço e estoque..."),
			);
			elements.checkoutBody.append(status);
		}
	} else if (state.phase === "confirmed" && state.result) {
		const status = el("div", "dialog-status dialog-status--confirmed");
		status.append(
			createIcon("check", { size: 15 }),
			document.createTextNode(
				"Compra confirmada no gateway. Abrimos o anúncio em uma nova aba.",
			),
		);
		elements.checkoutBody.append(status);
		addRow(
			"Total",
			formatBRL(state.result.total_amount),
			"summary__row--total",
		);
		addRow("Marketplace", marketplaceLabel(state.result.marketplace));
		addRow("Estoque restante", `${state.result.remaining_stock} un.`);
		elements.checkoutBody.append(summary);
		const link = safeHttpUrl(state.result.redirect_checkout_url);
		if (link) {
			const anchor = el("a", "dialog-link", "Abrir anúncio novamente");
			anchor.href = link;
			anchor.target = "_blank";
			anchor.rel = "noopener noreferrer";
			elements.checkoutBody.append(anchor);
		}
	} else if (state.phase === "conflict" && state.result) {
		const status = el("div", "dialog-status dialog-status--warning");
		status.append(
			createIcon("warning", { size: 15 }),
			document.createTextNode(state.result.message),
		);
		elements.checkoutBody.append(status);
		addRow("Preço atual", formatBRL(state.result.current_price));
		addRow("Estoque atual", `${state.result.current_stock} un.`);
		elements.checkoutBody.append(summary);
		if (state.result.status === "OUT_OF_STOCK") {
			const alternative = el(
				"button",
				"button button--ghost",
				"Pedir uma alternativa no chat",
			);
			alternative.type = "button";
			alternative.addEventListener("click", () => {
				checkoutState = null;
				elements.checkoutDialog.close();
				sendQuestion(
					`Quero uma alternativa ao produto ${state.card.name}.`,
				);
			});
			elements.checkoutBody.append(alternative);
		}
	} else if (state.phase === "error") {
		const status = el("div", "dialog-status dialog-status--error");
		status.append(
			createIcon("warning", { size: 15 }),
			document.createTextNode(state.error ?? "Erro no checkout."),
		);
		elements.checkoutBody.append(status);
		elements.checkoutBody.append(
			el(
				"p",
				"dialog-note",
				"Nenhuma compra foi registrada. Você pode tentar novamente.",
			),
		);
	}

	const pending = state.phase === "pending";
	elements.checkoutCancel.disabled = pending;
	elements.checkoutCancel.textContent =
		state.phase === "confirmed" ||
		state.phase === "conflict" ||
		state.phase === "error"
			? "Fechar"
			: "Cancelar";
	elements.checkoutConfirm.hidden =
		state.phase === "confirmed" ||
		(state.phase === "conflict" && state.result?.status === "OUT_OF_STOCK");
	elements.checkoutConfirm.disabled = pending;
	if (state.phase === "pending") {
		elements.checkoutConfirm.textContent = "Validando...";
	} else if (state.phase === "confirm") {
		elements.checkoutConfirm.textContent = `Comprar na ${marketplaceLabel(state.card.marketplace)}`;
	} else if (state.phase === "confirmed") {
		elements.checkoutConfirm.textContent = "Fechar";
	} else if (
		state.phase === "conflict" &&
		state.result?.status === "PRICE_CHANGED"
	) {
		elements.checkoutConfirm.textContent = `Aceitar ${formatBRL(state.result.current_price)} e continuar`;
	} else if (state.phase === "conflict") {
		elements.checkoutConfirm.textContent = "Fechar";
	} else if (state.phase === "error") {
		elements.checkoutConfirm.textContent = "Tentar novamente";
	}
}

async function confirmCheckout(displayedPrice) {
	const state = checkoutState;
	if (!state || state.pending || !state.message.serverMessageId) return;
	const sessionId = controller?.getState().sessionId;
	if (!sessionId) {
		state.phase = "error";
		state.error =
			"Sua sessão expirou. Faça a pergunta de novo para receber recomendações atualizadas.";
		renderCheckout();
		return;
	}

	state.pending = true;
	state.phase = "pending";
	state.acceptedPrice = displayedPrice;
	state.error = null;
	renderCheckout();

	try {
		const result = await api.postCheckout({
			session_id: sessionId,
			message_id: state.message.serverMessageId,
			sku: state.card.sku,
			recommendation_type: state.card.recommendation_type,
			quantity: 1,
			displayed_price: displayedPrice,
		});
		if (result.status === "CONFIRMED") {
			state.phase = "confirmed";
			state.result = result;
			state.card = {
				...state.card,
				price: result.confirmed_unit_price,
				stock_quantity: result.remaining_stock,
			};
			controller.patchProduct(state.card.sku, {
				price: result.confirmed_unit_price,
				stock_quantity: result.remaining_stock,
			});
			const redirect = safeHttpUrl(result.redirect_checkout_url);
			if (redirect) {
				try {
					await browser.tabs.create({ url: redirect });
				} catch (error) {
					console.warn("checkout_tab_open_failed", error);
				}
			}
		} else {
			state.phase = "conflict";
			state.result = result;
			state.card = {
				...state.card,
				price: result.current_price,
				stock_quantity: result.current_stock,
			};
			controller.patchProduct(state.card.sku, {
				price: result.current_price,
				stock_quantity: result.current_stock,
			});
		}
	} catch (error) {
		state.phase = "error";
		state.error = describeCheckoutError(error);
	} finally {
		state.pending = false;
		renderCheckout();
	}
}

function onCheckoutConfirm() {
	const state = checkoutState;
	if (!state || state.pending) return;
	if (state.phase === "confirm") {
		void confirmCheckout(state.acceptedPrice ?? state.card.price);
	} else if (state.phase === "confirmed") {
		elements.checkoutDialog.close();
	} else if (
		state.phase === "conflict" &&
		state.result?.status === "PRICE_CHANGED"
	) {
		void confirmCheckout(state.result.current_price);
	} else if (state.phase === "error") {
		void confirmCheckout(state.acceptedPrice ?? state.card.price);
	} else if (state.phase === "conflict") {
		elements.checkoutDialog.close();
	}
}

/* ------------------------------------------------------------------------- */
/* Wiring                                                                     */
/* ------------------------------------------------------------------------- */

function updateAnnouncement() {
	const lastAssistant = [...chatState.messages]
		.reverse()
		.find((message) => message.role === "assistant");
	if (!lastAssistant) return;
	if (lastAssistant.isStreaming && announcedMessageId === lastAssistant.id) {
		announcedMessageId = null;
		return;
	}
	if (lastAssistant.isStreaming || announcedMessageId === lastAssistant.id)
		return;
	if (!lastAssistant.content && !lastAssistant.errorFallback) return;
	const announcement = lastAssistant.errorFallback
		? `${fallbackInfo(lastAssistant.errorCode).title}. ${lastAssistant.errorFallback}`
		: lastAssistant.content;
	elements.chatAnnouncer.textContent = announcement;
	announcedMessageId = lastAssistant.id;
}

function handleChatState(state) {
	const wasRestored = chatState.restored;
	chatState = state;
	if (chatState.restored && !wasRestored) {
		// Do not re-announce an old answer when reopening the sidebar.
		const lastAssistant = [...chatState.messages]
			.reverse()
			.find((message) => message.role === "assistant");
		announcedMessageId = lastAssistant?.id ?? null;
	}
	renderMessages();
	renderNotice();
}

function renderAll() {
	renderNotice();
	renderContextBar();
	renderMessages();
	renderComposer();
	renderConnection();
}

function wireEvents() {
	elements.settingsButton.addEventListener("click", openOptions);
	elements.connectionAction.addEventListener("click", openOptions);
	elements.resetButton.addEventListener("click", () => {
		if (!controller) return;
		if (
			!window.confirm(
				"Reiniciar a conversa? O histórico desta sessão será encerrado.",
			)
		)
			return;
		expandedCitations = new Set();
		feedbackUi = new Map();
		announcedMessageId = null;
		lastMessageCount = 0;
		void controller.reset();
	});
	elements.noticeDismiss.addEventListener("click", () =>
		controller?.clearNotice(),
	);

	elements.composer.addEventListener("submit", (event) => {
		event.preventDefault();
		sendQuestion(elements.prompt.value);
	});
	elements.prompt.addEventListener("input", () => {
		autoResizePrompt();
		renderComposer();
	});
	elements.prompt.addEventListener("keydown", (event) => {
		if (event.key !== "Enter" || event.shiftKey || event.isComposing) return;
		event.preventDefault();
		sendQuestion(elements.prompt.value);
	});

	elements.checkoutClose.addEventListener("click", closeCheckout);
	elements.checkoutCancel.addEventListener("click", () => {
		if (
			checkoutState?.phase === "confirmed" ||
			checkoutState?.phase === "conflict"
		) {
			elements.checkoutDialog.close();
		} else {
			closeCheckout();
		}
	});
	elements.checkoutConfirm.addEventListener("click", onCheckoutConfirm);
	elements.checkoutDialog.addEventListener("cancel", (event) => {
		if (checkoutState?.pending) event.preventDefault();
	});
	elements.checkoutDialog.addEventListener("close", () => {
		checkoutState = null;
		elements.checkoutBody.replaceChildren();
	});

	browser.runtime.onMessage.addListener((message) => {
		if (message?.type !== "smartsales:product-context") return false;
		if (
			message.tabId !== null &&
			message.tabId !== undefined &&
			activeTabId !== null &&
			message.tabId !== activeTabId
		) {
			return false;
		}
		void applyDetection(message.product);
		return false;
	});

	browser.tabs.onActivated.addListener(({ tabId }) => {
		activeTabId = tabId;
		currentDetectionSignature = "";
		ignoredDetectionSignature = null;
		contextRequestCounter += 1;
		void refreshContextFromActiveTab();
	});

	browser.storage.onChanged.addListener(async (changes, areaName) => {
		if (areaName !== "local" || !changes[SETTINGS_STORAGE_KEY]) return;
		const previousBase = settings.apiBaseUrl;
		try {
			settings = await repository.getSettings();
		} catch (error) {
			console.warn("settings_reload_failed", error);
			return;
		}
		if (settings.apiBaseUrl !== previousBase) {
			healthState = "unknown";
		}
		renderConnection();
		renderComposer();
		if (settings.apiBaseUrl !== previousBase) {
			client = createApiClient({ baseUrl: settings.apiBaseUrl });
			void checkHealth();
			if (contextState.detection) retryContextDetection();
		}
	});
}

async function main() {
	installIcons();
	wireEvents();
	autoResizePrompt();
	renderAll();

	try {
		settings = await repository.getSettings();
	} catch (error) {
		console.warn("settings_load_failed", error);
	}
	client = createApiClient({ baseUrl: settings.apiBaseUrl });
	controller = new ChatSessionController({
		api,
		sessions: repository,
		getSettings: () => settings,
		onChange: handleChatState,
		maxAutomaticReconnects: MAX_AUTOMATIC_RECONNECTS,
	});
	chatState = controller.getState();
	renderAll();

	void checkHealth();
	void initializeContext();
	void controller.initialize();
	healthTimer = window.setInterval(() => {
		void checkHealth();
	}, HEALTH_INTERVAL_MS);
	window.addEventListener("unload", () => {
		window.clearInterval(healthTimer);
		controller?.destroy();
	});
}

void main();
