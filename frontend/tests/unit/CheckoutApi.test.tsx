import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { buildRecommendations, findProduct } from "@/lib/mock-data";
import type { ProductCardData } from "@/types/chat";

const API = "http://middleend.test";
const SERVER_SESSION = "11111111-1111-4111-8111-111111111111";
const SERVER_MESSAGE = "33333333-3333-4333-8333-333333333333";
const CHECKOUT_EVENT = "55555555-5555-4555-8555-555555555555";
const airfryer = findProduct("AF-400-220V")!;
const cards = buildRecommendations(airfryer);
const upsell = cards.find((card) => card.recommendation_type === "UPSELL")!;

const sse = (events: [string, unknown][]): Response =>
  new Response(events.map(([name, data]) => `event: ${name}\ndata: ${JSON.stringify(data)}\n\n`).join(""), {
    status: 200,
    headers: { "Content-Type": "text/event-stream" },
  });

const apiError = (status: number, code: string): Response =>
  Response.json({ error: { code, message: code, trace_id: "t", details: {} } }, { status });

const confirmed = (card: ProductCardData, price = card.price): Response =>
  Response.json({
    checkout_event_id: CHECKOUT_EVENT,
    status: "CONFIRMED",
    sku: card.sku,
    product_name: card.name,
    voltage: card.voltage,
    marketplace: card.marketplace,
    redirect_checkout_url: "https://lista.mercadolivre.com.br/airfryer-55",
    quantity: 1,
    confirmed_unit_price: price,
    total_amount: price,
    remaining_stock: 7,
    message: "Estoque validado.",
  });

const conflict = (card: ProductCardData, status: "PRICE_CHANGED" | "OUT_OF_STOCK", price: number, stock: number) =>
  Response.json(
    {
      checkout_event_id: CHECKOUT_EVENT,
      status,
      sku: card.sku,
      current_price: price,
      current_stock: stock,
      redirect_checkout_url: null,
      message: status === "OUT_OF_STOCK" ? "Item esgotado." : "Preço atualizado.",
    },
    { status: 409 }
  );

/** Real gateway stub; `checkoutResponses` are served in order. */
function stubGateway(checkoutResponses: (() => Response)[]) {
  const fetchMock = vi.fn(async (url: string, init?: RequestInit): Promise<Response> => {
    void init;
    if (url.endsWith("/api/v1/sessions")) {
      return Response.json({ session_id: SERVER_SESSION, restored: false, history: [], expires_in_seconds: 1800 }, { status: 201 });
    }
    if (url.endsWith("/api/v1/chat/stream")) {
      return sse([
        ["metadata", { message_id: SERVER_MESSAGE, session_id: SERVER_SESSION, cache_hit: false, ttft_ms: 120 }],
        ["token", { delta: "O modelo de 5,5L atende 6 pessoas." }],
        ["recommendations", { products: cards }],
        ["done", { finish_reason: "stop", total_latency_ms: 300, tokens_used: 10 }],
      ]);
    }
    if (url.endsWith("/api/v1/checkout/mock")) {
      const next = checkoutResponses.shift();
      if (!next) throw new Error("unexpected checkout call");
      return next();
    }
    throw new Error(`unexpected fetch ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

const checkoutBodies = (fetchMock: ReturnType<typeof stubGateway>): unknown[] =>
  fetchMock.mock.calls
    .filter(([url]) => url.endsWith("/api/v1/checkout/mock"))
    .map(([, init]) => JSON.parse(String(init?.body)));

async function renderCarousel() {
  // API_BASE_URL is read at import time, so load the component after stubbing the env.
  const { ProductRecommendationCarousel } = await import("@/components/shop/ProductRecommendationCarousel");
  render(<ProductRecommendationCarousel products={cards} sessionId={SERVER_SESSION} messageId={SERVER_MESSAGE} />);
}

beforeEach(() => {
  vi.resetModules();
  vi.stubEnv("NEXT_PUBLIC_API_BASE_URL", API);
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("UT-F04-01: card de recomendação", () => {
  it("mostra foto, voltagem, selo, preço em BRL, justificativa e CTA do marketplace", async () => {
    stubGateway([]);
    await renderCarousel();

    const card = screen.getByTestId(`recommendation-card-${upsell.sku}`);
    expect(within(card).getByRole("img", { name: upsell.name })).toHaveAttribute("src", upsell.image_url);
    expect(within(card).getByTestId(`voltage-${upsell.sku}`)).toHaveTextContent("220V");
    expect(within(card).getByText(upsell.badge_label)).toBeInTheDocument();
    expect(within(card).getByText("R$ 629,90")).toBeInTheDocument();
    expect(within(card).getByText(upsell.justification)).toBeInTheDocument();
    expect(within(card).getByTestId(`buy-now-btn-${upsell.sku}`)).toHaveTextContent("Comprar na Mercado Livre");
  });

  it("sem badge_label, o selo vem do recommendation_type", async () => {
    stubGateway([]);
    const { ProductRecommendationCarousel } = await import("@/components/shop/ProductRecommendationCarousel");
    render(
      <ProductRecommendationCarousel
        products={cards.map((card) => ({ ...card, badge_label: "" }))}
        sessionId={SERVER_SESSION}
        messageId={SERVER_MESSAGE}
      />
    );

    expect(screen.getByTestId(`recommendation-card-${airfryer.sku}`)).toHaveTextContent("Ideal");
    expect(screen.getByTestId(`recommendation-card-${upsell.sku}`)).toHaveTextContent("Upgrade");
    expect(screen.getByTestId("recommendation-card-KIT-SIL-01")).toHaveTextContent("Acessório");
  });
});

describe("UT-F04-02: mock checkout ligado ao POST /api/v1/checkout/mock", () => {
  it("envia o message_id do evento metadata, não o id local da bolha", async () => {
    const fetchMock = stubGateway([() => confirmed(upsell)]);
    const { ProductPageView } = await import("@/components/shop/ProductPageView");
    render(<ProductPageView product={airfryer} />);
    fireEvent.click(screen.getByTestId("quick-suggestion-0"));

    const carousel = await screen.findByTestId("recommendation-carousel");
    fireEvent.click(within(carousel).getByTestId(`buy-now-btn-${upsell.sku}`));

    await screen.findByTestId("checkout-confirmed");
    expect(checkoutBodies(fetchMock)).toEqual([
      {
        session_id: SERVER_SESSION,
        message_id: SERVER_MESSAGE,
        sku: upsell.sku,
        recommendation_type: "UPSELL",
        quantity: 1,
        displayed_price: upsell.price,
      },
    ]);
    const [url, init] = fetchMock.mock.calls.find(([called]) => called.endsWith("/api/v1/checkout/mock"))!;
    expect(url).toBe(`${API}/api/v1/checkout/mock`);
    expect(init?.method).toBe("POST");
  });

  it("200 mostra preço confirmado, total, estoque restante e link seguro para o marketplace", async () => {
    stubGateway([() => confirmed(upsell)]);
    await renderCarousel();
    fireEvent.click(screen.getByTestId(`buy-now-btn-${upsell.sku}`));

    const confirmation = await screen.findByTestId("checkout-confirmed");
    expect(within(confirmation).getAllByText("R$ 629,90")).toHaveLength(2);
    expect(within(confirmation).getByText("7 un.")).toBeInTheDocument();
    const link = screen.getByTestId("checkout-redirect-link");
    expect(link).toHaveAttribute("href", "https://lista.mercadolivre.com.br/airfryer-55");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link.getAttribute("rel")).toContain("noopener");
  });

  it("409 PRICE_CHANGED mostra o novo preço e reenvia só depois que o usuário confirma", async () => {
    const fetchMock = stubGateway([() => conflict(upsell, "PRICE_CHANGED", 659.9, 8), () => confirmed(upsell, 659.9)]);
    await renderCarousel();
    fireEvent.click(screen.getByTestId(`buy-now-btn-${upsell.sku}`));

    const changed = await screen.findByTestId("checkout-conflict");
    expect(changed).toHaveTextContent("R$ 659,90");
    expect(screen.queryByTestId("checkout-redirect-link")).not.toBeInTheDocument();
    expect(checkoutBodies(fetchMock)).toHaveLength(1);

    fireEvent.click(screen.getByRole("button", { name: /Confirmar por R\$\s659,90/ }));

    await screen.findByTestId("checkout-confirmed");
    const [first, second] = checkoutBodies(fetchMock);
    expect(first).toMatchObject({ displayed_price: 629.9 });
    expect(second).toMatchObject({ displayed_price: 659.9, message_id: SERVER_MESSAGE });
  });

  it("409 OUT_OF_STOCK mostra indisponível, sem link, e desabilita o card", async () => {
    stubGateway([() => conflict(upsell, "OUT_OF_STOCK", 629.9, 0)]);
    await renderCarousel();
    fireEvent.click(screen.getByTestId(`buy-now-btn-${upsell.sku}`));

    const unavailable = await screen.findByTestId("checkout-conflict");
    expect(unavailable).toHaveTextContent(/esgotado/i);
    expect(unavailable).toHaveTextContent("0 un.");
    expect(screen.queryByTestId("checkout-redirect-link")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Confirmar por/ })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Entendi" }));
    const card = screen.getByTestId(`recommendation-card-${upsell.sku}`);
    expect(within(card).getByTestId(`buy-now-btn-${upsell.sku}`)).toBeDisabled();
    expect(card).toHaveTextContent(/Esgotado/);
  });

  it.each([
    [404, "PRODUCT_NOT_FOUND", /não está mais disponível/i],
    [410, "SESSION_EXPIRED", /sessão expirou/i],
    [422, "VALIDATION_ERROR", /não pôde ser validado/i],
    [429, "RATE_LIMITED", /aguarde/i],
    [503, "SERVICE_UNAVAILABLE", /indisponível/i],
  ])("HTTP %i mostra mensagem amigável e permite tentar de novo", async (status, code, text) => {
    const fetchMock = stubGateway([() => apiError(status, code), () => confirmed(upsell)]);
    await renderCarousel();
    fireEvent.click(screen.getByTestId(`buy-now-btn-${upsell.sku}`));

    expect(await screen.findByTestId("checkout-error")).toHaveTextContent(text);
    fireEvent.click(screen.getByRole("button", { name: "Tentar novamente" }));

    await screen.findByTestId("checkout-confirmed");
    const [failed, retried] = checkoutBodies(fetchMock);
    expect(retried).toEqual(failed);
  });
});
