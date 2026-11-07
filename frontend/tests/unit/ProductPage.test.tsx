import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { ProductPageView } from "@/components/shop/ProductPageView";
import { suggestionsFor } from "@/components/chat/ProductAssistant";
import { findProduct } from "@/lib/mock-data";

const mockCheckout = vi.hoisted(() => vi.fn(() => new Promise<never>(() => {})));
vi.mock("@/lib/mock-api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/mock-api")>()),
  mockCheckout,
}));

const product = (sku: string) => {
  const found = findProduct(sku);
  if (!found) throw new Error(`Produto ${sku} ausente no mock`);
  return found;
};

describe("Página do produto com Consultor IA ao lado", () => {
  it("mostra galeria, ficha técnica, sobre o item e o consultor ancorado no SKU", () => {
    render(<ProductPageView product={product("AF-400-220V")} />);

    expect(screen.getByRole("heading", { level: 1, name: "Airfryer SmartChef 4L" })).toBeInTheDocument();
    const specs = screen.getByTestId("product-specs");
    expect(within(specs).getByText("1500 W")).toBeInTheDocument();
    expect(within(specs).getByText("4 L")).toBeInTheDocument();
    expect(screen.getByText("Sobre este item")).toBeInTheDocument();

    const assistant = screen.getByTestId("product-assistant");
    expect(assistant).toHaveAttribute("data-sku", "AF-400-220V");
    expect(within(assistant).getByText(/Perguntas frequentes deste produto/i)).toBeInTheDocument();
  });

  it("troca a foto principal pela miniatura escolhida", () => {
    render(<ProductPageView product={product("AF-400-220V")} />);

    expect(screen.getByTestId("product-main-image")).toHaveAttribute("src", "/images/airfryer-4l.svg");
    fireEvent.click(screen.getByRole("tab", { name: "Foto 2 de 2" }));
    expect(screen.getByTestId("product-main-image")).toHaveAttribute(
      "src",
      "/images/airfryer-4l-painel.svg"
    );
  });

  it("abre e fecha o consultor no celular pelo botão flutuante", () => {
    render(<ProductPageView product={product("AF-400-220V")} />);

    expect(screen.queryByTestId("contextual-chat-drawer")).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId("open-assistant-btn"));
    expect(screen.getByTestId("contextual-chat-drawer")).toHaveAttribute("data-sku", "AF-400-220V");
    fireEvent.click(screen.getByTestId("close-drawer-btn"));
    expect(screen.queryByTestId("contextual-chat-drawer")).not.toBeInTheDocument();
  });

  it("registra um único checkout mesmo quando a página re-renderiza", () => {
    const airfryer = product("AF-400-220V");
    const { rerender } = render(<ProductPageView product={airfryer} />);

    fireEvent.click(screen.getByTestId("buy-btn-AF-400-220V"));
    rerender(<ProductPageView product={airfryer} />);

    expect(mockCheckout).toHaveBeenCalledTimes(1);
  });

  it("sugere perguntas coerentes com o tipo de produto", () => {
    expect(suggestionsFor(product("CF-15B-127V"))).toContain("Como faço a descalcificação?");
    expect(suggestionsFor(product("AF-400-220V"))).toContain(
      "Quais materiais de forma e assadeira posso utilizar?"
    );
    expect(suggestionsFor(product("KIT-SIL-01"))).toContain("Como devo fazer a limpeza?");
  });
});
