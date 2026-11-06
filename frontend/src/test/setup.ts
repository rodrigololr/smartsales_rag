import "@testing-library/jest-dom";
import { vi } from "vitest";

// Polyfill scrollIntoView para JSDOM
if (typeof window !== "undefined") {
  window.HTMLElement.prototype.scrollIntoView = vi.fn();
}
