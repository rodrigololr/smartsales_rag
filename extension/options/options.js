/**
 * Options page: configures the gateway origin and per-turn filters. Values are
 * stored in `browser.storage.local`; the sidebar listens to storage changes.
 */

import { createApiClient } from "../src/infrastructure/gateway-api.js";
import {
	DEFAULT_SETTINGS,
	createSettingsRepository,
	parseApiBaseUrl,
} from "../src/infrastructure/settings.js";

const repository = createSettingsRepository({
	localArea: browser.storage.local,
	sessionArea: browser.storage.session ?? browser.storage.local,
});

const elements = {
	version: document.getElementById("version"),
	apiUrl: document.getElementById("api-url"),
	preferredVoltage: document.getElementById("preferred-voltage"),
	budgetMax: document.getElementById("budget-max"),
	floatingButton: document.getElementById("floating-button"),
	testButton: document.getElementById("test-button"),
	testResult: document.getElementById("test-result"),
	connectionStatus: document.getElementById("connection-status"),
	saveButton: document.getElementById("save-button"),
	resetDefaults: document.getElementById("reset-defaults"),
	openConsultor: document.getElementById("open-consultor"),
	saveStatus: document.getElementById("save-status"),
};

/**
 * @param {HTMLElement} element
 * @param {"ok" | "warning" | "error" | "neutral"} state
 * @param {string} text
 */
function setStatus(element, state, text) {
	element.textContent = text;
	element.dataset.state = state;
}

/**
 * @param {import("../src/infrastructure/settings.js").ExtensionSettings} settings
 */
function fillForm(settings) {
	elements.apiUrl.value = settings.apiBaseUrl;
	elements.preferredVoltage.value = settings.preferredVoltage ?? "";
	elements.budgetMax.value =
		settings.budgetMax === null || settings.budgetMax === undefined
			? ""
			: String(settings.budgetMax);
	elements.floatingButton.checked = settings.showFloatingButton;
}

/**
 * @returns {{ apiBaseUrl: string | null, budgetMax: number | null, error: string | null }}
 */
function readForm() {
	const apiBaseUrl = parseApiBaseUrl(elements.apiUrl.value);
	if (!apiBaseUrl) {
		return {
			apiBaseUrl: null,
			budgetMax: null,
			error: "Informe uma URL http(s) válida, sem query, hash ou credenciais.",
		};
	}
	const budgetRaw = elements.budgetMax.value.trim();
	const budgetMax = budgetRaw === "" ? null : Number(budgetRaw);
	if (budgetMax !== null && (!Number.isFinite(budgetMax) || budgetMax <= 0)) {
		return {
			apiBaseUrl: null,
			budgetMax: null,
			error: "O orçamento máximo deve ser um número maior que zero.",
		};
	}
	return { apiBaseUrl, budgetMax, error: null };
}

async function hasHostPermission(apiBaseUrl) {
	if (!browser.permissions?.contains) return true;
	try {
		const origin = new URL(apiBaseUrl).origin;
		return await browser.permissions.contains({ origins: [`${origin}/*`] });
	} catch (error) {
		console.warn("permission_check_failed", error);
		return true;
	}
}

async function saveSettings() {
	const form = readForm();
	if (form.error || !form.apiBaseUrl) {
		setStatus(
			elements.saveStatus,
			"error",
			form.error ?? "Revise os campos.",
		);
		elements.apiUrl.focus();
		return;
	}
	const permitted = await hasHostPermission(form.apiBaseUrl);
	if (!permitted) {
		setStatus(
			elements.saveStatus,
			"error",
			"Permita o acesso a sites em about:addons → Consultor SmartSales → Permissões e dados.",
		);
		return;
	}

	elements.saveButton.disabled = true;
	try {
		const settings = await repository.saveSettings({
			apiBaseUrl: form.apiBaseUrl,
			showFloatingButton: elements.floatingButton.checked,
			preferredVoltage:
				elements.preferredVoltage.value === "127V" ||
				elements.preferredVoltage.value === "220V"
					? elements.preferredVoltage.value
					: null,
			budgetMax: form.budgetMax,
		});
		fillForm(settings);
		setStatus(elements.saveStatus, "ok", "Configurações salvas.");
		setStatus(elements.connectionStatus, "neutral", "Ainda não testada");
		elements.testResult.textContent = "";
		elements.testResult.dataset.state = "";
	} catch (error) {
		console.warn("settings_save_failed", error);
		setStatus(
			elements.saveStatus,
			"error",
			"Não foi possível salvar as configurações.",
		);
	} finally {
		elements.saveButton.disabled = false;
	}
}

async function testConnection() {
	const form = readForm();
	if (form.error || !form.apiBaseUrl) {
		setStatus(elements.testResult, "error", form.error ?? "URL inválida.");
		setStatus(elements.connectionStatus, "error", "URL inválida");
		return;
	}
	elements.testButton.disabled = true;
	setStatus(elements.testResult, "neutral", "Testando...");
	setStatus(elements.connectionStatus, "neutral", "Testando");
	try {
		const client = createApiClient({ baseUrl: form.apiBaseUrl });
		const health = await client.health();
		if (health.status === "ok") {
			setStatus(elements.connectionStatus, "ok", "Conectado");
			const components = health.components
				? Object.entries(health.components)
						.map(([name, status]) => `${name}: ${status}`)
						.join(" · ")
				: "";
			setStatus(
				elements.testResult,
				"ok",
				`Gateway respondeu${health.version ? ` (v${health.version})` : ""}${components ? ` — ${components}` : ""}.`,
			);
		} else {
			setStatus(elements.connectionStatus, "warning", "Degradado");
			setStatus(
				elements.testResult,
				"warning",
				"O gateway respondeu, mas algum componente está indisponível. O chat pode falhar.",
			);
		}
	} catch (error) {
		setStatus(elements.connectionStatus, "error", "Sem conexão");
		setStatus(
			elements.testResult,
			"error",
			error instanceof Error
				? error.message
				: "Não foi possível falar com o gateway.",
		);
	} finally {
		elements.testButton.disabled = false;
	}
}

function restoreDefaults() {
	fillForm({ ...DEFAULT_SETTINGS });
	setStatus(
		elements.saveStatus,
		"warning",
		"Padrões preenchidos. Clique em Salvar para aplicar.",
	);
}

async function openConsultor() {
	try {
		await browser.runtime.sendMessage({ type: "smartsales:open-consultor" });
	} catch (error) {
		console.warn("open_consultor_message_failed", error);
		await browser.tabs.create({
			url: browser.runtime.getURL("sidebar/sidebar.html"),
		});
	}
}

function wireEvents() {
	elements.saveButton.addEventListener("click", () => void saveSettings());
	elements.testButton.addEventListener("click", () => void testConnection());
	elements.resetDefaults.addEventListener("click", restoreDefaults);
	elements.openConsultor.addEventListener("click", () => void openConsultor());
	elements.apiUrl.addEventListener("input", () => {
		elements.saveStatus.textContent = "";
		elements.saveStatus.dataset.state = "";
	});
	elements.budgetMax.addEventListener("input", () => {
		elements.saveStatus.textContent = "";
		elements.saveStatus.dataset.state = "";
	});
}

async function main() {
	elements.version.textContent = `v${browser.runtime.getManifest().version}`;
	wireEvents();
	try {
		const settings = await repository.getSettings();
		fillForm(settings);
	} catch (error) {
		console.warn("settings_load_failed", error);
		fillForm({ ...DEFAULT_SETTINGS });
		setStatus(
			elements.saveStatus,
			"error",
			"Não foi possível carregar as configurações salvas.",
		);
	}
}

void main();
