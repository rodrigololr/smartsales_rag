import { expect, test } from "@playwright/test";

import {
  AIRFRYER_4L,
  AIRFRYER_55L,
  CACHE_HIT_LIMIT_MS,
  CHAT_STREAM_PATH,
  CHECKOUT_PATH,
  FEEDBACK_PATH,
  FIRST_TEXT_SMOKE_LIMIT_MS,
  SESSIONS_PATH,
  SILICONE_KIT,
  answerText,
  ask,
  openProduct,
  shownTtftMs,
  waitForDone,
} from "./support";

/**
 * Jornadas E2E-01 a E2E-08 de specs/tdd_and_quality/02_test_cases_unit_int_e2e.md.
 * Rodam contra a pilha real (docker compose), com LLM e manuais de demonstração.
 * As jornadas que dependem de rotas ainda não implementadas no gateway ficam em
 * `test.fixme`, com o pacote que as destrava.
 */

test("E2E-01: dúvida técnica com streaming SSE e citação da página do manual", async ({ page }) => {
  const assistant = await openProduct(page, AIRFRYER_4L);

  const answer = await ask(assistant, "Posso usar formas de alumínio no cesto?");
  await expect(answerText(answer)).toBeVisible({ timeout: FIRST_TEXT_SMOKE_LIMIT_MS });
  await waitForDone(assistant);

  const badge = answer.locator('[data-testid^="citation-badge-"]').first();
  await expect(badge).toContainText("Manual Airfryer SmartChef 4L");
  await expect(badge).toContainText(/p\. ?\d+/);

  await expect(badge).toHaveAttribute("aria-expanded", "false");
  await badge.click();
  await expect(badge).toHaveAttribute("aria-expanded", "true");
  const excerpt = page.locator(`[id="${await badge.getAttribute("aria-controls")}"]`);
  await expect(excerpt).toBeVisible();
  await expect(excerpt).toContainText(/p[aá]gina \d+/i);
  await expect(excerpt).toContainText(/alumínio/i);
});

test("E2E-02: família grande recebe upsell e cross-sell em estoque", async ({ page }) => {
  const assistant = await openProduct(page, AIRFRYER_4L);

  const answer = await ask(assistant, "A capacidade de 4L atende uma família de 5 pessoas?");
  await waitForDone(assistant);

  const carousel = answer.getByTestId("recommendation-carousel");
  await expect(carousel).toBeVisible();
  const cards = carousel.locator('[data-testid^="recommendation-card-"]');
  await expect(cards).toHaveCount(3);
  await expect(carousel.getByTestId(`recommendation-card-${AIRFRYER_4L}`)).toContainText("Produto Consultado");
  await expect(carousel.getByTestId(`recommendation-card-${AIRFRYER_55L}`)).toContainText("Upgrade Recomendado");
  await expect(carousel.getByTestId(`recommendation-card-${SILICONE_KIT}`)).toContainText("Compre Junto Compatível");
  await expect(carousel.getByTestId(`recommendation-card-${AIRFRYER_55L}`)).toContainText("220V");
  const marketplaceBySku = {
    [AIRFRYER_4L]: "Amazon",
    [AIRFRYER_55L]: "Mercado Livre",
    [SILICONE_KIT]: "Shopee",
  };
  for (const [sku, marketplace] of Object.entries(marketplaceBySku)) {
    const buy = carousel.getByTestId(`buy-now-btn-${sku}`);
    await expect(buy).toBeEnabled();
    await expect(buy).toContainText(marketplace);
  }
});

test("E2E-03: conversão pelo mock checkout com link do marketplace", async ({ page }) => {
  const assistant = await openProduct(page, AIRFRYER_4L);
  const answer = await ask(assistant, "A capacidade de 4L atende uma família de 5 pessoas?");
  await waitForDone(assistant);

  const checkout = page.waitForResponse(
    (response) => response.request().method() === "POST" && response.url().endsWith(CHECKOUT_PATH)
  );
  await answer.getByTestId(`buy-now-btn-${AIRFRYER_55L}`).click();
  const request = (await checkout).request().postDataJSON() as { message_id: string; sku: string };
  expect(request.sku).toBe(AIRFRYER_55L);

  await expect(page.getByTestId("checkout-confirmed")).toBeVisible();
  const redirect = page.getByTestId("checkout-redirect-link");
  await expect(redirect).toHaveAttribute("href", /^https:\/\//);
  await expect(redirect).toHaveAttribute("target", "_blank");
});

test.fixme("E2E-04: estoque zerado antes do clique em Comprar agora", async () => {
  // Depende de POST /api/v1/checkout/mock com 409 OUT_OF_STOCK (pacote M05, issue #16).
});

const UNANSWERABLE_QUESTIONS = {
  "técnica ausente do manual": "Qual é a pressão da bomba em bar?",
  "fora do domínio": "Qual é a cotação do dólar hoje e o resultado do último jogo?",
};

for (const [kind, question] of Object.entries(UNANSWERABLE_QUESTIONS)) {
  test(`E2E-05: pergunta ${kind} recebe fallback seguro, sem números inventados`, async ({ page }) => {
    const assistant = await openProduct(page, AIRFRYER_4L);

    const answer = await ask(assistant, question);
    await waitForDone(assistant);

    const fallback = answer.locator('[data-testid^="assistant-fallback-"]');
    await expect(fallback).toBeVisible();
    await expect(fallback).toContainText("LOW_SIMILARITY_FALLBACK");
    await expect(answer.getByTestId("citation-list")).toHaveCount(0);
    await expect(answerText(answer)).toHaveCount(0);

    // Regra 2: o fallback vem seguido de itens similares em estoque, validados no SQL.
    const carousel = answer.getByTestId("recommendation-carousel");
    await expect(carousel).toBeVisible();
    const buyButtons = carousel.locator('[data-testid^="buy-now-btn-"]');
    expect(await buyButtons.count()).toBeGreaterThan(0);
    for (const buy of await buyButtons.all()) {
      await expect(buy).toBeEnabled();
    }
  });
}

test("E2E-06 (cache): a mesma pergunta em nova sessão volta por cache hit", async ({ page }) => {
  const question = "Qual é a voltagem oficial deste modelo (220V)?";
  const assistant = await openProduct(page, AIRFRYER_4L);
  await ask(assistant, question);
  await waitForDone(assistant);

  await assistant.getByTestId("reset-chat-btn").click();
  await expect(assistant.getByTestId("quick-suggestion-0")).toBeVisible();
  const repeated = await ask(assistant, question);
  await waitForDone(assistant);

  await expect(repeated.getByText("Cache", { exact: true })).toBeVisible();
  expect(await shownTtftMs(repeated)).toBeLessThan(CACHE_HIT_LIMIT_MS);
});

test("E2E-06 (feedback): like persistido no banco", async ({ page }) => {
  const assistant = await openProduct(page, AIRFRYER_4L);
  const answer = await ask(assistant, "Posso usar formas de alumínio no cesto?");
  await waitForDone(assistant);

  const recorded = page.waitForResponse(
    (response) => response.request().method() === "POST" && response.url().endsWith(FEEDBACK_PATH)
  );
  await answer.locator('[data-testid^="feedback-like-"]').click();

  expect((await recorded).status()).toBe(201);
  await expect(answer.getByText("Obrigado pelo feedback!")).toBeVisible();
});

test("E2E-07: reiniciar a conversa encerra a sessão e não herda o contexto", async ({ page }) => {
  const assistant = await openProduct(page, AIRFRYER_4L);
  const firstRequest = page.waitForRequest((request) => request.url().endsWith(CHAT_STREAM_PATH));
  await ask(assistant, "Como faço a limpeza do cesto?");
  const firstSession = (await firstRequest).postDataJSON().session_id as string;
  await waitForDone(assistant);

  const ended = page.waitForResponse(
    (response) =>
      response.request().method() === "DELETE" &&
      response.url().endsWith(`/api/v1/sessions/${firstSession}`),
  );
  await assistant.getByTestId("reset-chat-btn").click();
  expect((await ended).status()).toBe(204);
  await expect(assistant.locator('[data-testid^="assistant-message-"]')).toHaveCount(0);
  await expect(assistant.getByTestId("quick-suggestion-0")).toBeVisible();

  const created = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" && response.url().endsWith(SESSIONS_PATH),
  );
  const secondRequest = page.waitForRequest((request) => request.url().endsWith(CHAT_STREAM_PATH));
  await ask(assistant, "E a garantia?");
  const newSession = (await (await created).json()) as { session_id: string; history: unknown[] };
  expect(newSession.history, "a nova sessão nasce sem o histórico anterior").toEqual([]);
  const secondSession = (await secondRequest).postDataJSON().session_id as string;
  expect(secondSession).toBe(newSession.session_id);
  expect(secondSession).not.toBe(firstSession);
  await waitForDone(assistant);
});

test("E2E-08: painel de métricas com ADMIN_TOKEN após a ingestão", async ({ page }) => {
  const adminToken = process.env.E2E_ADMIN_TOKEN;
  test.skip(!adminToken, "defina E2E_ADMIN_TOKEN com o ADMIN_TOKEN do gateway");

  await page.goto("/admin/metricas");
  await page.getByTestId("admin-token-input").fill("token-errado");
  await page.getByTestId("admin-token-submit").click();
  await expect(page.getByTestId("admin-error")).toBeVisible();

  await page.getByTestId("admin-token-input").fill(adminToken ?? "");
  await page.getByTestId("admin-token-submit").click();
  await expect(page.getByTestId("admin-dashboard")).toBeVisible();
  expect(page.url()).not.toContain(adminToken ?? "");
});
