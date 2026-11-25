import { describe, expect, it } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { CatalogView } from "@/components/catalog/CatalogView";
import { ConsultantProvider } from "@/components/chat/ConsultantProvider";
import { CATALOG_SUGGESTIONS } from "@/components/chat/ProductAssistant";
import { ProductPageView } from "@/components/shop/ProductPageView";
import { CATALOG_PRODUCTS } from "@/lib/mock-data";

describe("UT-F01-01: catálogo comum com imagens", () => {
  it("mostra os produtos com foto, preço e link para a página do item", () => {
    render(<CatalogView products={CATALOG_PRODUCTS} />);

    expect(within(screen.getByRole("banner")).getByText(/SmartSales/i)).toBeInTheDocument();
    const card = screen.getByTestId("product-card-AF-400-220V");
    expect(card).toHaveAttribute("href", "/produto/AF-400-220V");
    expect(within(card).getByRole("img", { name: "Airfryer SmartChef 4L" })).toHaveAttribute(
      "src",
      "/images/airfryer-4l.svg"
    );
    expect(within(card).getByText("R$ 499,90")).toBeInTheDocument();
    expect(screen.queryByTestId("product-assistant")).not.toBeInTheDocument();
  });

  it("filtra por voltagem e busca", () => {
    render(<CatalogView products={CATALOG_PRODUCTS} />);

    fireEvent.click(screen.getByRole("button", { name: "127V" }));
    expect(screen.getByTestId("product-card-CF-15B-127V")).toBeInTheDocument();
    expect(screen.queryByTestId("product-card-AF-400-220V")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Todas" }));
    fireEvent.change(screen.getByLabelText("Buscar produtos no catálogo"), {
      target: { value: "família" },
    });
    expect(screen.getByText("Nenhum produto encontrado")).toBeInTheDocument();
  });

  it("Bivolt tem filtro próprio e aparece, rotulado, em 127V e em 220V", () => {
    const bivolt = { ...CATALOG_PRODUCTS[0], sku: "SEC-BIV", name: "Secador Bivolt", voltage: "BIVOLT" as const };
    render(<CatalogView products={[...CATALOG_PRODUCTS, bivolt]} />);

    for (const filter of ["127V", "220V"]) {
      fireEvent.click(screen.getByRole("button", { name: filter }));
      expect(screen.getByTestId("product-card-SEC-BIV")).toBeInTheDocument();
      expect(within(screen.getByTestId("product-card-SEC-BIV")).getByText("Bivolt")).toBeInTheDocument();
      expect(screen.getByText(/Inclui modelos bivolt/)).toBeInTheDocument();
    }

    fireEvent.click(screen.getByRole("button", { name: "Bivolt" }));
    expect(screen.getByTestId("product-card-SEC-BIV")).toBeInTheDocument();
    expect(screen.queryByTestId("product-card-AF-400-220V")).not.toBeInTheDocument();
    expect(screen.queryByTestId("product-card-CF-15B-127V")).not.toBeInTheDocument();
    expect(screen.queryByText(/Inclui modelos bivolt/)).not.toBeInTheDocument();
  });

  it("mantém os históricos do catálogo e de cada produto separados ao navegar", async () => {
    const { rerender } = render(
      <ConsultantProvider>
        <CatalogView products={CATALOG_PRODUCTS} />
      </ConsultantProvider>
    );

    fireEvent.click(screen.getByTestId("open-assistant-btn"));

    const drawer = screen.getByTestId("contextual-chat-drawer");
    const assistantInDrawer = within(drawer).getByTestId("product-assistant");
    expect(within(assistantInDrawer).getByText("Catálogo completo")).toBeInTheDocument();
    expect(
      within(assistantInDrawer).getByText("Catálogo, manuais e base de conhecimento")
    ).toBeInTheDocument();
    for (const suggestion of CATALOG_SUGGESTIONS) {
      expect(within(assistantInDrawer).getByText(suggestion)).toBeInTheDocument();
    }

    fireEvent.click(within(drawer).getByTestId("quick-suggestion-0"));
    expect(await within(drawer).findByTestId("assistant-text")).toHaveTextContent(
      "O consultor do catálogo exige a API real."
    );

    rerender(
      <ConsultantProvider>
        <ProductPageView product={CATALOG_PRODUCTS[0]} />
      </ConsultantProvider>
    );

    const dockedAssistant = screen.getByTestId("product-assistant");
    expect(within(dockedAssistant).queryByTestId("assistant-text")).not.toBeInTheDocument();
    const question = "Qual é a voltagem da primeira airfryer?";
    const field = within(dockedAssistant).getByTestId("chat-prompt-input");
    fireEvent.change(field, { target: { value: question } });
    fireEvent.click(within(dockedAssistant).getByRole("button", { name: "Enviar pergunta" }));
    expect(await within(dockedAssistant).findByTestId("assistant-text")).toBeInTheDocument();

    rerender(
      <ConsultantProvider>
        <ProductPageView product={CATALOG_PRODUCTS[1]} />
      </ConsultantProvider>
    );
    expect(screen.queryByText(question)).not.toBeInTheDocument();

    rerender(
      <ConsultantProvider>
        <ProductPageView product={CATALOG_PRODUCTS[0]} />
      </ConsultantProvider>
    );
    expect(screen.getByText(question)).toBeInTheDocument();
    expect(screen.queryByText(CATALOG_SUGGESTIONS[0])).not.toBeInTheDocument();

    rerender(
      <ConsultantProvider>
        <CatalogView products={CATALOG_PRODUCTS} />
      </ConsultantProvider>
    );
    fireEvent.click(screen.getByTestId("open-assistant-btn"));
    expect(screen.getByTestId("assistant-text")).toHaveTextContent(
      "O consultor do catálogo exige a API real."
    );
  });
});
