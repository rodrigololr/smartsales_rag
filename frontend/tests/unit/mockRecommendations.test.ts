import { describe, expect, it } from "vitest";
import type { StreamEvent } from "@/types/chat";
import { CATALOG_PRODUCTS, RECOMMENDATION_PRODUCTS, buildRecommendations, findProduct } from "@/lib/mock-data";
import { streamMockChat } from "@/lib/mock-api";

const ALL = [...CATALOG_PRODUCTS, ...RECOMMENDATION_PRODUCTS];
const UPSELL_MAX_PRICE_RATIO = 1.35;

describe("Motor de recomendação do modo mock", () => {
  it.each(ALL.map((product) => [product.sku, product] as const))(
    "%s: upsell nunca é o próprio item nem de tier menor; sem SKUs repetidos",
    (_sku, base) => {
      const cards = buildRecommendations(base);
      expect(new Set(cards.map((card) => card.sku)).size).toBe(cards.length);
      expect(cards[0]).toMatchObject({ sku: base.sku, recommendation_type: "PRIMARY" });

      const upsell = cards.find((card) => card.recommendation_type === "UPSELL");
      if (upsell) {
        const upsellProduct = findProduct(upsell.sku)!;
        expect(upsell.sku).not.toBe(base.sku);
        expect(upsellProduct.subcategory).toBe(base.subcategory);
        expect(upsellProduct.capacity_liters ?? 0).toBeGreaterThan(base.capacity_liters ?? 0);
        expect(upsell.price).toBeGreaterThan(base.price);
        expect(upsell.price).toBeLessThanOrEqual(base.price * UPSELL_MAX_PRICE_RATIO);
        expect(upsell.stock_quantity).toBeGreaterThan(0);
      }
      const cross = cards.find((card) => card.recommendation_type === "CROSS_SELL");
      if (cross) expect(findProduct(cross.sku)!.category).toBe("Acessórios");
    }
  );

  it("escolhe o próximo tier acima dentro do teto de +35%", () => {
    const upsellOf = (sku: string) =>
      buildRecommendations(findProduct(sku)!).find((card) => card.recommendation_type === "UPSELL")?.sku;
    expect(upsellOf("AF-400-220V")).toBe("AF-550-220V");
    expect(upsellOf("AF-550-220V")).toBe("AF-800-220V");
    expect(upsellOf("AF-800-220V")).toBeUndefined();
    expect(upsellOf("CF-15B-127V")).toBe("CF-20B-127V");
    expect(upsellOf("CF-20B-127V")).toBeUndefined();
  });

  it("subcategoria que o mock não conhece responde LOW_SIMILARITY_FALLBACK", async () => {
    const events: StreamEvent[] = [];
    for await (const event of streamMockChat({
      sessionId: "s",
      message: "Como devo fazer a limpeza?",
      product: findProduct("KIT-CAF-01")!,
    })) {
      events.push(event);
    }
    expect(events.map((event) => event.event)).toEqual(["metadata", "error", "recommendations", "done"]);
    expect(events[1]).toMatchObject({ data: { code: "LOW_SIMILARITY_FALLBACK" } });
    // Only the item itself as the purchase card: no airfryer/coffee answers or upsell for it.
    expect(events[2]).toMatchObject({ data: { products: [{ sku: "KIT-CAF-01", recommendation_type: "PRIMARY" }] } });
  });

  it("modo catálogo sem produto emite token fixo exigindo a API real seguido de done", async () => {
    const events: StreamEvent[] = [];
    for await (const event of streamMockChat({
      sessionId: "s",
      message: "Quero um computador novo",
      product: null,
    })) {
      events.push(event);
    }
    expect(events).toEqual([
      { event: "token", data: { delta: "O consultor do catálogo exige a API real." } },
      { event: "done", data: expect.objectContaining({ finish_reason: "stop" }) },
    ]);
  });
});
