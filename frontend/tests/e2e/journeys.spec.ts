import { expect, test } from "@playwright/test";

import {
  AIRFRYER_4L,
  AIRFRYER_55L,
  CACHE_HIT_LIMIT_MS,
  SILICONE_KIT,
  TTFT_LIMIT_MS,
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

  const sentAt = Date.now();
  const answer = await ask(assistant, "Posso usar formas de alumínio no cesto?");
  const text = answer.locator("div.whitespace-pre-wrap");
  await expect(text).toBeVisible({ timeout: 30_000 });
  const firstTokenMs = Date.now() - sentAt;
  await waitForDone(assistant);

  expect(firstTokenMs, "primeiro token visível no navegador").toBeLessThanOrEqual(TTFT_LIMIT_MS);
  const badge = answer.locator('[data-testid^="citation-badge-"]').first();
  await expect(badge).toContainText("Manual Airfryer SmartChef 4L");
  await expect(badge).toContainText(/p\. ?\d+/);

  await badge.click();
  const dialog = page.getByTestId("citation-dialog");
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText("Manual Airfryer SmartChef 4L");
  await expect(dialog).toContainText(/alumínio/i);
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
  for (const sku of [AIRFRYER_4L, AIRFRYER_55L, SILICONE_KIT]) {
    await expect(carousel.getByTestId(`buy-now-btn-${sku}`)).toBeEnabled();
  }
});

test.fixme("E2E-03: conversão pelo mock checkout com link do marketplace", async () => {
  // Depende de POST /api/v1/checkout/mock no gateway (pacote M05, issue #16).
});

test.fixme("E2E-04: estoque zerado antes do clique em Comprar agora", async () => {
  // Depende de POST /api/v1/checkout/mock com 409 OUT_OF_STOCK (pacote M05, issue #16).
});

test("E2E-05: pergunta fora do manual recebe fallback seguro, sem números inventados", async ({ page }) => {
  const assistant = await openProduct(page, AIRFRYER_4L);

  const answer = await ask(assistant, "Qual é a cotação do dólar hoje e o resultado do último jogo?");
  await waitForDone(assistant);

  const fallback = answer.locator('[data-testid^="assistant-fallback-"]');
  await expect(fallback).toBeVisible();
  await expect(fallback).toContainText("LOW_SIMILARITY_FALLBACK");
  await expect(answer.getByTestId("citation-list")).toHaveCount(0);
  await expect(answer.locator("div.whitespace-pre-wrap")).toHaveCount(0);
});

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

test.fixme("E2E-06 (feedback): like persistido no banco", async () => {
  // Depende de POST /api/v1/feedback no gateway (pacote F03/M04, issues #12 e #15).
});

test("E2E-07: reiniciar a conversa encerra a sessão e não herda o contexto", async ({ page }) => {
  const assistant = await openProduct(page, AIRFRYER_4L);
  const firstRequest = page.waitForRequest((request) => request.url().endsWith("/api/v1/chat/stream"));
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

  const secondRequest = page.waitForRequest((request) => request.url().endsWith("/api/v1/chat/stream"));
  await ask(assistant, "E a garantia?");
  const secondSession = (await secondRequest).postDataJSON().session_id as string;
  expect(secondSession).not.toBe(firstSession);
  await waitForDone(assistant);
});

test.fixme("E2E-08: painel de métricas com ADMIN_TOKEN após a ingestão", async () => {
  // Depende de GET /api/v1/metrics/summary no gateway (pacote M04, issue #15).
});
