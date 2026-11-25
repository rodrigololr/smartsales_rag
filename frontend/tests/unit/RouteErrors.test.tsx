import { describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { fireEvent, render, screen } from "@testing-library/react";
import GlobalError from "@/app/global-error";

vi.mock("next/font/google", () => ({ Inter: () => ({ variable: "inter-variable" }) }));
import StoreError from "@/app/error";

describe("Erros de rota", () => {
  it("error.tsx mostra a mensagem e chama retry() do Next", () => {
    const retry = vi.fn();
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    render(<StoreError error={new Error("boom")} retry={retry} />);

    expect(screen.getByRole("alert")).toHaveTextContent(/Não foi possível abrir esta página/);
    fireEvent.click(screen.getByRole("button", { name: /Tentar novamente/ }));
    expect(retry).toHaveBeenCalledOnce();
  });

  it("global-error.tsx renderiza o próprio <html>/<body> com a mesma mensagem", () => {
    const markup = renderToStaticMarkup(<GlobalError error={new Error("boom")} retry={() => undefined} />);

    expect(markup).toMatch(/^<html lang="pt-BR"[^>]*>(<head>.*<\/head>)?<body/);
    expect(markup).toContain('class="font-sans inter-variable"');
    expect(markup).toContain("Não foi possível abrir esta página");
    expect(markup).toContain("Tentar novamente");
  });
});
