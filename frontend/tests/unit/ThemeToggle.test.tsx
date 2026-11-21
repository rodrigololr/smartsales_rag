import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { ThemeSync, ThemeToggle } from "@/components/layout/ThemeToggle";
import { THEME_STORAGE_KEY, themeInitScript } from "@/lib/theme";

type Listener = (event: { matches: boolean }) => void;

/** matchMedia stub whose "(prefers-color-scheme: dark)" answer can change at runtime. */
function mockSystemTheme(initiallyDark: boolean) {
  const listeners = new Set<Listener>();
  const query = {
    matches: initiallyDark,
    addEventListener: (_type: string, listener: Listener) => listeners.add(listener),
    removeEventListener: (_type: string, listener: Listener) => listeners.delete(listener),
  };
  window.matchMedia = vi.fn().mockReturnValue(query) as unknown as typeof window.matchMedia;
  return {
    setDark(dark: boolean) {
      query.matches = dark;
      listeners.forEach((listener) => listener({ matches: dark }));
    },
  };
}

const html = () => document.documentElement;

describe("Tema claro/escuro", () => {
  beforeEach(() => {
    localStorage.clear();
    html().classList.remove("dark");
  });

  afterEach(() => {
    Reflect.deleteProperty(window, "matchMedia");
  });

  it("começa em Sistema e persiste a escolha aplicando a classe .dark no <html>", () => {
    mockSystemTheme(false);
    render(<ThemeToggle />);

    expect(screen.getByRole("group", { name: "Tema" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Tema do sistema" })).toHaveAttribute("aria-pressed", "true");

    fireEvent.click(screen.getByRole("button", { name: "Tema escuro" }));
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe("dark");
    expect(html()).toHaveClass("dark");
    expect(screen.getByRole("button", { name: "Tema escuro" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Tema do sistema" })).toHaveAttribute("aria-pressed", "false");

    fireEvent.click(screen.getByRole("button", { name: "Tema claro" }));
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe("light");
    expect(html()).not.toHaveClass("dark");
  });

  it("restaura a escolha salva ao montar", () => {
    mockSystemTheme(false);
    localStorage.setItem(THEME_STORAGE_KEY, "dark");
    render(<ThemeToggle />);
    expect(screen.getByRole("button", { name: "Tema escuro" })).toHaveAttribute("aria-pressed", "true");
  });

  it("em Sistema acompanha prefers-color-scheme, inclusive quando ele muda", () => {
    const system = mockSystemTheme(true);
    localStorage.setItem(THEME_STORAGE_KEY, "light");
    render(
      <>
        <ThemeSync />
        <ThemeToggle />
      </>
    );

    fireEvent.click(screen.getByRole("button", { name: "Tema do sistema" }));
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBeNull();
    expect(html()).toHaveClass("dark");

    act(() => system.setDark(false));
    expect(html()).not.toHaveClass("dark");
  });

  it("reaplica o tema quando o React recria a classe do <html> (ex.: 404 renderizado no cliente)", () => {
    mockSystemTheme(false);
    localStorage.setItem(THEME_STORAGE_KEY, "dark");
    render(<ThemeSync />);
    expect(html()).toHaveClass("dark");
  });

  it("o script inline aplica o tema antes da pintura (salvo > sistema)", () => {
    mockSystemTheme(true);
    new Function(themeInitScript)();
    expect(html()).toHaveClass("dark");

    localStorage.setItem(THEME_STORAGE_KEY, "light");
    new Function(themeInitScript)();
    expect(html()).not.toHaveClass("dark");
  });

  it("funciona mesmo sem acesso ao localStorage", () => {
    mockSystemTheme(true);
    const getItem = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("SecurityError");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("SecurityError");
    });

    new Function(themeInitScript)();
    expect(html()).toHaveClass("dark");

    render(<ThemeToggle />);
    expect(screen.getByRole("button", { name: "Tema do sistema" })).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(screen.getByRole("button", { name: "Tema claro" }));
    expect(html()).not.toHaveClass("dark");
    expect(screen.getByRole("button", { name: "Tema claro" })).toHaveAttribute("aria-pressed", "true");
    expect(getItem).toHaveBeenCalled();
    vi.restoreAllMocks();
  });
});
