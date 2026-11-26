/**
 * Small inline SVG icon factory (no remote assets, no innerHTML with data).
 * @typedef {"spark" | "chat" | "gear" | "reset" | "send" | "book" | "check" | "warning" | "info" | "close" | "cart" | "external" | "thumbs-up" | "thumbs-down" | "trash" | "bolt"} IconName
 */

const PATHS = {
  spark: [
    ["path", { d: "M12 3v4M12 17v4M3 12h4M17 12h4M5.6 5.6l2.8 2.8M15.6 15.6l2.8 2.8M18.4 5.6l-2.8 2.8M8.4 15.6l-2.8 2.8" }],
  ],
  chat: [
    ["path", { d: "M21 11.5a8.4 8.4 0 0 1-8.5 8.3 9 9 0 0 1-3.8-.8L3 21l1.9-5.1a8 8 0 0 1-1.4-4.4A8.4 8.4 0 0 1 12 3.2a8.4 8.4 0 0 1 9 8.3Z" }],
    ["path", { d: "M8.5 11.5h7M8.5 8.5h4" }],
  ],
  gear: [
    ["circle", { cx: "12", cy: "12", r: "3" }],
    ["path", { d: "M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-2.8 2.8-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.6v.2h-4V21a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1L4.2 17l.1-.1a1.7 1.7 0 0 0 .3-1.9A1.7 1.7 0 0 0 3 14H2.8v-4H3a1.7 1.7 0 0 0 1.6-1 1.7 1.7 0 0 0-.3-1.9L4.2 7 7 4.2l.1.1a1.7 1.7 0 0 0 1.9.3A1.7 1.7 0 0 0 10 3V2.8h4V3a1.7 1.7 0 0 0 1 1.6 1.7 1.7 0 0 0 1.9-.3l.1-.1L19.8 7l-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.6 1h.2v4H21a1.7 1.7 0 0 0-1.6 1Z" }],
  ],
  reset: [
    ["path", { d: "M3 12a9 9 0 1 0 3-6.7" }],
    ["path", { d: "M3 4v5h5" }],
  ],
  send: [
    ["path", { d: "m22 2-7 20-4-9-9-4Z" }],
    ["path", { d: "M22 2 11 13" }],
  ],
  book: [
    ["path", { d: "M4 19.5A2.5 2.5 0 0 1 6.5 17H20" }],
    ["path", { d: "M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2Z" }],
  ],
  check: [
    ["path", { d: "m20 6-11 11-5-5" }],
  ],
  warning: [
    ["path", { d: "M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z" }],
    ["path", { d: "M12 9v4M12 17h.01" }],
  ],
  info: [
    ["circle", { cx: "12", cy: "12", r: "9" }],
    ["path", { d: "M12 11v5M12 8h.01" }],
  ],
  close: [
    ["path", { d: "M18 6 6 18M6 6l12 12" }],
  ],
  cart: [
    ["circle", { cx: "9", cy: "20", r: "1" }],
    ["circle", { cx: "19", cy: "20", r: "1" }],
    ["path", { d: "M2 3h3l2.4 11.4a2 2 0 0 0 2 1.6h7.7a2 2 0 0 0 2-1.6L21 7H6" }],
  ],
  external: [
    ["path", { d: "M15 3h6v6M10 14 21 3" }],
    ["path", { d: "M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" }],
  ],
  "thumbs-up": [
    ["path", { d: "M7 10v11H4a1 1 0 0 1-1-1v-9a1 1 0 0 1 1-1h3Z" }],
    ["path", { d: "M7 10l4-7a2 2 0 0 1 3 1.8V9h5a2 2 0 0 1 2 2.3l-1.2 7A2 2 0 0 1 17.8 20H7" }],
  ],
  "thumbs-down": [
    ["path", { d: "M17 14V3h3a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1h-3Z" }],
    ["path", { d: "M17 14l-4 7a2 2 0 0 1-3-1.8V15H5a2 2 0 0 1-2-2.3l1.2-7A2 2 0 0 1 6.2 4H17" }],
  ],
  trash: [
    ["path", { d: "M3 6h18M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" }],
    ["path", { d: "M10 11v6M14 11v6" }],
  ],
  bolt: [
    ["path", { d: "M13 2 3 14h7l-1 8 11-14h-7l0-6Z" }],
  ],
};

/**
 * @param {IconName} name
 * @param {{ size?: number, className?: string }} [options]
 * @returns {SVGSVGElement}
 */
export function createIcon(name, options = {}) {
  const size = options.size ?? 16;
  const namespace = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(namespace, "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("width", String(size));
  svg.setAttribute("height", String(size));
  svg.setAttribute("fill", "none");
  svg.setAttribute("stroke", "currentColor");
  svg.setAttribute("stroke-width", "2");
  svg.setAttribute("stroke-linecap", "round");
  svg.setAttribute("stroke-linejoin", "round");
  svg.setAttribute("aria-hidden", "true");
  if (options.className) svg.setAttribute("class", options.className);
  for (const [tag, attributes] of PATHS[name] ?? []) {
    const child = document.createElementNS(namespace, tag);
    for (const [attribute, value] of Object.entries(attributes)) {
      child.setAttribute(attribute, value);
    }
    svg.append(child);
  }
  return svg;
}
