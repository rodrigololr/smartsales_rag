import { expect, test } from "@playwright/test";
import {
  AIRFRYER_4L,
  AIRFRYER_55L,
  CHAT_STREAM_PATH,
  SESSIONS_PATH,
  waitForDone,
} from "./support";

const SESSION_ID = "11111111-1111-4111-8111-111111111111";

const sseBody = (events: [string, unknown][]): string =>
  events.map(([name, data]) => `event: ${name}\ndata: ${JSON.stringify(data)}\n\n`).join("");

test("E2E Consultor Unificado (P4): home -> pergunta -> cards OPTION -> Ver detalhes -> página do produto mantém histórico e envia current_product_sku", async ({
  page,
}) => {
  const sessionBodies: Record<string, unknown>[] = [];
  const streamBodies: Record<string, unknown>[] = [];

  await page.route(`**${SESSIONS_PATH}`, async (route) => {
    if (route.request().method() !== "POST") {
      await route.fallback();
      return;
    }
    sessionBodies.push((route.request().postDataJSON() ?? {}) as Record<string, unknown>);
    await route.fulfill({
      status: 201,
      contentType: "application/json",
      body: JSON.stringify({
        session_id: SESSION_ID,
        restored: false,
        history: [],
        expires_in_seconds: 1800,
      }),
    });
  });

  await page.route(`**${CHAT_STREAM_PATH}`, async (route) => {
    const body = (route.request().postDataJSON() ?? {}) as Record<string, unknown>;
    streamBodies.push(body);
    const turn = streamBodies.length;

    const events: [string, unknown][] =
      turn === 1
        ? [
            [
              "metadata",
              {
                message_id: "22222222-2222-4222-8222-222222222221",
                session_id: SESSION_ID,
                cache_hit: false,
                ttft_ms: 45,
              },
            ],
            ["token", { delta: "Encontrei 2 opções em estoque no catálogo:" }],
            [
              "recommendations",
              {
                products: [
                  {
                    sku: AIRFRYER_4L,
                    name: "Airfryer SmartChef 4L",
                    price: 499.9,
                    stock_quantity: 15,
                    voltage: "220V",
                    capacity_liters: 4.0,
                    power_watts: 1500,
                    image_url: "/images/airfryer-4l.svg",
                    marketplace: "AMAZON",
                    checkout_url: "https://www.amazon.com.br/s?k=Airfryer+SmartChef+4L",
                    recommendation_type: "OPTION",
                    badge_label: "Opção",
                    justification: "4 L, 1500 W.",
                  },
                  {
                    sku: AIRFRYER_55L,
                    name: "Airfryer SmartChef 5.5L Family",
                    price: 629.9,
                    stock_quantity: 8,
                    voltage: "220V",
                    capacity_liters: 5.5,
                    power_watts: 1800,
                    image_url: "/images/airfryer-55l.svg",
                    marketplace: "MERCADO_LIVRE",
                    checkout_url: "https://lista.mercadolivre.com.br/Airfryer-SmartChef-5.5L",
                    recommendation_type: "OPTION",
                    badge_label: "Opção",
                    justification: "5,5 L, 1800 W.",
                  },
                ],
              },
            ],
            ["done", { finish_reason: "stop", total_latency_ms: 120, tokens_used: 12 }],
          ]
        : [
            [
              "metadata",
              {
                message_id: "22222222-2222-4222-8222-222222222222",
                session_id: SESSION_ID,
                cache_hit: false,
                ttft_ms: 38,
              },
            ],
            ["token", { delta: "A potência nominal deste modelo é de 1500 W." }],
            ["done", { finish_reason: "stop", total_latency_ms: 95, tokens_used: 10 }],
          ];

    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: sseBody(events),
    });
  });

  await page.goto("/");

  const drawer = page.getByTestId("contextual-chat-drawer");
  await expect(async () => {
    await page.getByTestId("open-assistant-btn").click();
    await expect(drawer).toBeVisible({ timeout: 2_000 });
  }).toPass();

  const homeAssistant = drawer.getByTestId("product-assistant");
  await expect(homeAssistant).toContainText("Catálogo completo");
  await expect(homeAssistant).toContainText("Catálogo, manuais e base de conhecimento");

  await homeAssistant.getByTestId("chat-prompt-input").fill("Quero opções de airfryer em estoque");
  await homeAssistant.getByTestId("chat-prompt-input").press("Enter");
  await waitForDone(homeAssistant);

  await expect(homeAssistant).toContainText("Encontrei 2 opções em estoque no catálogo:");
  const optionCard = homeAssistant.getByTestId(`recommendation-card-${AIRFRYER_4L}`);
  await expect(optionCard).toBeVisible();
  await expect(optionCard).toContainText("Opção");

  const viewDetails = optionCard.getByTestId(`view-details-${AIRFRYER_4L}`);
  await expect(viewDetails).toHaveAttribute("href", `/produto/${AIRFRYER_4L}`);
  await viewDetails.click();

  await expect(page).toHaveURL(new RegExp(`/produto/${AIRFRYER_4L}$`));

  const productAssistant = page
    .locator(`[data-testid="product-assistant"][data-sku="${AIRFRYER_4L}"]`)
    .filter({ visible: true })
    .first();
  const openAssistant = page.getByTestId("open-assistant-btn");
  if (await openAssistant.isVisible()) {
    await expect(async () => {
      await openAssistant.click();
      await expect(productAssistant).toBeVisible({ timeout: 2_000 });
    }).toPass();
  }
  await expect(productAssistant).toBeVisible();

  // The conversation started on the home page is preserved on the product page.
  await expect(productAssistant).toContainText("Quero opções de airfryer em estoque");
  await expect(productAssistant).toContainText("Encontrei 2 opções em estoque no catálogo:");

  await productAssistant.getByTestId("chat-prompt-input").fill("Qual é a potência deste modelo?");
  await productAssistant.getByTestId("chat-prompt-input").press("Enter");
  await waitForDone(productAssistant);

  await expect(productAssistant).toContainText("A potência nominal deste modelo é de 1500 W.");

  expect(sessionBodies).toEqual([{}]);
  expect(streamBodies).toHaveLength(2);
  expect(streamBodies[0]).toMatchObject({
    session_id: SESSION_ID,
    message: "Quero opções de airfryer em estoque",
  });
  expect(streamBodies[0]).not.toHaveProperty("context_filters");
  expect(streamBodies[1]).toMatchObject({
    session_id: SESSION_ID,
    message: "Qual é a potência deste modelo?",
    context_filters: { current_product_sku: AIRFRYER_4L },
  });
});
