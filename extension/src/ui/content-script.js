/**
 * Content script: detects the product identity already published by the page
 * (JSON-LD/meta/microdata) and offers a floating shortcut to the consultant.
 * It never sends page text or form data to the Gateway.
 */
(function () {
	"use strict";

	const detection = globalThis.SmartSalesProductDetection;
	if (!detection) return;

	const SETTINGS_STORAGE_KEY = "smartsales:settings";
	const LAUNCHER_HOST_ID = "smartsales-consultor-launcher";
	const DETECTION_DEBOUNCE_MS = 600;
	/** @type {ReturnType<typeof detection.detectProduct>} */
	let currentProduct = null;
	let currentSignature = "";
	let showFloatingButton = true;
	let detectionTimer = 0;
	let lastUrl = location.href;

	/**
	 * @returns {Promise<boolean>}
	 */
	async function readLauncherSetting() {
		try {
			const stored = await browser.storage.local.get(SETTINGS_STORAGE_KEY);
			const settings = stored[SETTINGS_STORAGE_KEY];
			return !settings || settings.showFloatingButton !== false;
		} catch {
			return true;
		}
	}

	/**
	 * @param {ReturnType<typeof detection.detectProduct>} product
	 * @returns {string}
	 */
	function signatureOf(product) {
		return product
			? `${location.href}|${product.sku ?? ""}|${product.name ?? ""}`
			: `${location.href}|`;
	}

	/**
	 * @param {ReturnType<typeof detection.detectProduct>} product
	 */
	function notifyBackground(product) {
		void browser.runtime
			.sendMessage({ type: "smartsales:page-product", product })
			.catch(() => {
				// Background not ready or extension reloading.
			});
	}

	function removeLauncher() {
		document.getElementById(LAUNCHER_HOST_ID)?.remove();
	}

	/**
	 * @param {NonNullable<ReturnType<typeof detection.detectProduct>>} product
	 */
	function mountLauncher(product) {
		if (document.getElementById(LAUNCHER_HOST_ID)) return;
		if (!document.body) return;

		const host = document.createElement("div");
		host.id = LAUNCHER_HOST_ID;
		host.style.all = "initial";
		const shadow = host.attachShadow({ mode: "closed" });
		const style = document.createElement("style");
		style.textContent = `
      :host { all: initial; }
      .launcher {
        position: fixed;
        right: 20px;
        bottom: 20px;
        z-index: 2147483647;
        display: inline-flex;
        align-items: center;
        gap: 8px;
        max-width: min(320px, calc(100vw - 40px));
        padding: 10px 14px;
        border: 1px solid #4338ca;
        border-radius: 999px;
        background: #4f46e5;
        color: #ffffff;
        box-shadow: 0 10px 30px rgba(30, 27, 75, 0.32);
        font: 600 13px/1.2 Inter, system-ui, -apple-system, "Segoe UI", sans-serif;
        cursor: pointer;
        transition: transform 120ms ease, background-color 120ms ease;
      }
      .launcher:hover { background: #4338ca; transform: translateY(-1px); }
      .launcher:focus-visible {
        outline: 3px solid #c7d2fe;
        outline-offset: 2px;
      }
      .launcher svg { width: 18px; height: 18px; flex: none; }
      .launcher span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
      @media (max-width: 480px) {
        .launcher { right: 12px; bottom: 12px; padding: 11px; }
        .launcher span { display: none; }
      }
      @media (prefers-reduced-motion: reduce) {
        .launcher { transition: none; }
      }
    `;

		const button = document.createElement("button");
		button.type = "button";
		button.className = "launcher";
		button.title = product.name
			? `Perguntar ao Consultor SmartSales sobre ${product.name}`
			: "Abrir o Consultor SmartSales";
		button.setAttribute(
			"aria-label",
			product.name
				? `Perguntar ao Consultor SmartSales sobre ${product.name}`
				: "Abrir o Consultor SmartSales",
		);
		const svgNamespace = "http://www.w3.org/2000/svg";
		const svg = document.createElementNS(svgNamespace, "svg");
		svg.setAttribute("viewBox", "0 0 24 24");
		svg.setAttribute("aria-hidden", "true");
		svg.setAttribute("fill", "none");
		svg.setAttribute("stroke", "currentColor");
		svg.setAttribute("stroke-width", "2");
		svg.setAttribute("stroke-linecap", "round");
		svg.setAttribute("stroke-linejoin", "round");
		const outline = document.createElementNS(svgNamespace, "path");
		outline.setAttribute(
			"d",
			"M21 11.5a8.4 8.4 0 0 1-8.5 8.3 9 9 0 0 1-3.8-.8L3 21l1.9-5.1a8 8 0 0 1-1.4-4.4A8.4 8.4 0 0 1 12 3.2a8.4 8.4 0 0 1 9 8.3Z",
		);
		const lines = document.createElementNS(svgNamespace, "path");
		lines.setAttribute("d", "M8.5 11.5h7M8.5 8.5h4");
		svg.append(outline, lines);
		const label = document.createElement("span");
		label.textContent = "Consultar com IA";
		button.append(svg, label);

		button.addEventListener("click", () => {
			void browser.runtime
				.sendMessage({
					type: "smartsales:open-consultor",
					product: currentProduct,
				})
				.catch(() => {
					// The extension may have been reloaded; the toolbar button still works.
				});
		});

		shadow.append(style, button);
		document.body.appendChild(host);
	}

	function updateLauncher() {
		if (currentProduct && showFloatingButton) {
			mountLauncher(currentProduct);
		} else {
			removeLauncher();
		}
	}

	function refreshDetection() {
		lastUrl = location.href;
		const snapshot = detection.collectPageSnapshot(document, lastUrl);
		const nextProduct = detection.detectProduct(snapshot);
		const nextSignature = signatureOf(nextProduct);
		if (nextSignature !== currentSignature) {
			currentProduct = nextProduct;
			currentSignature = nextSignature;
			updateLauncher();
			notifyBackground(nextProduct);
		} else if (!document.getElementById(LAUNCHER_HOST_ID)) {
			updateLauncher();
		}
	}

	function scheduleDetection() {
		window.clearTimeout(detectionTimer);
		detectionTimer = window.setTimeout(
			refreshDetection,
			DETECTION_DEBOUNCE_MS,
		);
	}

	browser.runtime.onMessage.addListener((message, _sender, sendResponse) => {
		if (message?.type === "smartsales:detect-product") {
			// Read on demand: a background/sidebar query may arrive before the
			// initial debounced detection or after an SPA swap.
			sendResponse(
				detection.detectProduct(
					detection.collectPageSnapshot(document, location.href),
				),
			);
			return false;
		}
		return false;
	});

	browser.storage.onChanged.addListener((changes, areaName) => {
		if (areaName !== "local" || !changes[SETTINGS_STORAGE_KEY]) return;
		const next = changes[SETTINGS_STORAGE_KEY].newValue;
		showFloatingButton = !next || next.showFloatingButton !== false;
		updateLauncher();
	});

	const RELEVANT_SELECTOR = [
		'script[type="application/ld+json"]',
		"meta[property]",
		"meta[itemprop]",
		'[itemtype*="Product"]',
		"[data-sku]",
		"[data-product-sku]",
		"title",
	].join(",");

	/**
	 * Storefronts mutate constantly (carousels, price tickers). Only a DOM change
	 * that can carry product identity should trigger a fresh snapshot.
	 * @param {MutationRecord} mutation
	 * @returns {boolean}
	 */
	function isRelevantMutation(mutation) {
		if (mutation.type === "attributes") return true;
		if (mutation.type !== "childList") return false;
		for (const node of [...mutation.addedNodes, ...mutation.removedNodes]) {
			if (node.nodeType !== Node.ELEMENT_NODE) continue;
			const element = /** @type {Element} */ (node);
			if (
				element.matches(RELEVANT_SELECTOR) ||
				element.querySelector(RELEVANT_SELECTOR)
			) {
				return true;
			}
		}
		return false;
	}

	const observer = new MutationObserver((mutations) => {
		if (location.href !== lastUrl) {
			refreshDetection();
			return;
		}
		if (mutations.some(isRelevantMutation)) scheduleDetection();
	});
	observer.observe(document.documentElement, {
		childList: true,
		subtree: true,
		attributes: true,
		attributeFilter: ["content", "data-sku", "data-product-sku", "itemprop"],
	});

	window.addEventListener("popstate", refreshDetection);
	window.addEventListener("hashchange", refreshDetection);
	// Some SPAs change history without a DOM mutation; a cheap URL poll covers it.
	window.setInterval(() => {
		if (location.href !== lastUrl) refreshDetection();
	}, 2000);

	void readLauncherSetting().then((enabled) => {
		showFloatingButton = enabled;
		refreshDetection();
	});
})();
