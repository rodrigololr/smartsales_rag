import { describe, expect, it } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { ProductRecommendationCarousel } from "@/components/shop/ProductRecommendationCarousel";
import { buildRecommendations, findProduct } from "@/lib/mock-data";

const base = findProduct("AF-400-220V");

describe("UT-F04-01: ProductRecommendationCarousel e Mock Checkout", () => {
  it("renderiza PRIMARY, UPSELL e CROSS_SELL e confirma o checkout", async () => {
    if (!base) throw new Error("Produto base ausente no mock");
    const cards = buildRecommendations(base);

    render(
      <ProductRecommendationCarousel
        products={cards}
        sessionId="session-test"
        messageId="message-test"
      />
    );

    expect(screen.getByTestId("recommendation-card-AF-400-220V")).toBeInTheDocument();
    expect(screen.getByTestId("recommendation-card-AF-550-220V")).toBeInTheDocument();
    expect(screen.getByTestId("recommendation-card-KIT-SIL-01")).toBeInTheDocument();
    expect(screen.getByText("Produto Consultado")).toBeInTheDocument();
    expect(
      screen.getByText("Upgrade Recomendado — Maior Capacidade")
    ).toBeInTheDocument();
    expect(screen.getByText("Compre Junto Compatível")).toBeInTheDocument();
    expect(screen.getByText("R$ 629,90")).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("buy-now-btn-AF-550-220V"));

    const confirmation = await screen.findByTestId("checkout-confirmed", undefined, {
      timeout: 3000,
    });
    expect(confirmation).toBeInTheDocument();
    expect(screen.getByText(/Compra confirmada/i)).toBeInTheDocument();
    expect(screen.getByTestId("checkout-redirect-link")).toHaveAttribute(
      "href",
      expect.stringContaining("mercadolivre.com.br")
    );
  });
});
