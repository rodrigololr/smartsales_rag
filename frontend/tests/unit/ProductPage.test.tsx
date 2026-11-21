import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { ProductPageView } from "@/components/shop/ProductPageView";
import { suggestionsFor } from "@/components/chat/ProductAssistant";
import { findProduct } from "@/lib/mock-data";
import { specsJsonRows } from "@/lib/format";
import type { ApiProduct } from "@/types/catalog";

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
    // specs_json from the catalog, humanized, units preserved (R01: only data).
    expect(within(specs).getByText("Temperatura máx.")).toBeInTheDocument();
    expect(within(specs).getByText("200 °C")).toBeInTheDocument();
    expect(within(specs).getByText("Timer máx.")).toBeInTheDocument();
    expect(within(specs).getByText("60 min")).toBeInTheDocument();
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

  it("o buy box (fora do chat) abre o marketplace direto, sem mock checkout", () => {
    render(<ProductPageView product={product("AF-400-220V")} />);

    const buy = screen.getByTestId("buy-btn-AF-400-220V");
    expect(buy).toHaveAttribute("href", expect.stringContaining("amazon.com.br"));
    expect(buy).toHaveAttribute("target", "_blank");
    fireEvent.click(buy);

    expect(mockCheckout).not.toHaveBeenCalled();
  });

  it("o buy box não cria link para checkout_url fora de http/https", () => {
    render(<ProductPageView product={{ ...product("AF-400-220V"), checkout_url: "javascript:alert(1)" }} />);

    expect(screen.queryByTestId("buy-btn-AF-400-220V")).not.toBeInTheDocument();
  });

  it("sugere perguntas coerentes com o tipo de produto", () => {
    expect(suggestionsFor(product("CF-15B-127V"))).toContain("Como faço a descalcificação?");
    expect(suggestionsFor(product("AF-400-220V"))).toContain(
      "Quais materiais de forma e assadeira posso utilizar?"
    );
    expect(suggestionsFor(product("KIT-SIL-01"))).toContain("Como devo fazer a limpeza?");
  });

  it("não sugere voltagem nem assadeira para itens fora desse contexto", () => {
    const headset = { ...product("KIT-SIL-01"), voltage: "N/A" as const, subcategory: "Headsets" };
    const blender = { ...product("AF-400-220V"), subcategory: "Liquidificadores", capacity_liters: 2 };
    expect(suggestionsFor(headset).join(" ")).not.toMatch(/voltagem/i);
    expect(suggestionsFor(blender).join(" ")).not.toMatch(/assadeira/i);
  });

  it("mostra 'Não se aplica' em vez de N/A e esconde o selo de voltagem", () => {
    render(<ProductPageView product={{ ...product("KIT-SIL-01"), voltage: "N/A" }} />);
    const specs = screen.getByTestId("product-specs");
    expect(within(specs).getByText("Não se aplica")).toBeInTheDocument();
    expect(screen.queryByText("N/A")).not.toBeInTheDocument();
  });
});

describe("specsJsonRows", () => {
  it("humaniza a chave, preserva a unidade e ignora valores não escalares", () => {
    expect(
      specsJsonRows({ pressao_bar: 15, frequencia_hz: 60, cesto_removivel: true, extra: null, lista: [1] })
    ).toEqual([
      ["Pressão", "15 bar"],
      ["Frequência", "60 Hz"],
      ["Cesto removível", "Sim"],
    ]);
    expect(specsJsonRows({ temperatura_min_c: 80, capacidade_l: 1.5 })).toEqual([
      ["Temperatura mín.", "80 °C"],
      ["Capacidade", "1,5 L"],
    ]);
    expect(
      specsJsonRows({ desligamento_automatico: true, cesto_lavavel: true, valvula_seguranca: true, numero_funcoes: 8 })
    ).toEqual([
      ["Desligamento automático", "Sim"],
      ["Cesto lavável", "Sim"],
      ["Válvula segurança", "Sim"],
      ["Número funções", "8"],
    ]);
    expect(
      specsJsonRows({ conexao: "USB", iluminacao: "RGB", bateria_horas: 200, dpi_max: 4000, validade_meses: 24 })
    ).toEqual([
      ["Conexão", "USB"],
      ["Iluminação", "RGB"],
      ["Bateria", "200 h"],
      ["DPI máx.", "4.000"],
      ["Validade", "24 meses"],
    ]);
    expect(
      specsJsonRows({ memoria_ram_gb: 16, tela_polegadas: 24, taxa_fps: 60, tempo_resposta_ms: 1 })
    ).toEqual([
      ["Memoria ram", "16 GB"],
      ["Tela", "24 ″"],
      ["Taxa", "60 fps"],
      ["Tempo resposta", "1 ms"],
    ]);
    expect(specsJsonRows(undefined)).toEqual([]);
  });

  it("produto do gateway: a descrição opcional aparece em 'Sobre este item'", () => {
    const gatewayProduct: ApiProduct = {
      sku: "SEC-AUR-2200",
      name: "Secador Aurélia 2200W",
      price: 289.9,
      stock_quantity: 4,
      voltage: "BIVOLT",
      capacity_liters: null,
      power_watts: 2200,
      image_url: "/images/secador-aurelia-2200w.svg",
      marketplace: "LOJA_OFICIAL",
      checkout_url: "https://loja.example.com/secador",
      category: "Cosméticos",
      subcategory: "Secadores",
      brand: "Aurélia",
      specs_json: {},
      updated_at: "2026-11-20T10:00:00Z",
      description: "Secador profissional com íons e 3 temperaturas.",
    };
    const { unmount } = render(<ProductPageView product={gatewayProduct} />);
    const about = screen.getByRole("region", { name: "Sobre este item" });
    expect(about).toHaveTextContent("Secador profissional com íons e 3 temperaturas.");
    unmount();

    render(<ProductPageView product={{ ...gatewayProduct, description: null }} />);
    expect(screen.queryByRole("region", { name: "Sobre este item" })).not.toBeInTheDocument();
  });
});
