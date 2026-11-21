import { expect, test, type Page, type Response } from "@playwright/test";
import type { Checkout, MetricsSummary } from "../../src/types/chat";
import { AIRFRYER_4L, CHECKOUT_PATH, FEEDBACK_PATH, answerText, ask, openProduct, waitForDone } from "./support";

const METRICS_PATH = "/api/v1/metrics/summary";
test.setTimeout(120_000);

function waitForResponse(page: Page, method: string, path: string): Promise<Response> {
  return page.waitForResponse((response) =>
    response.request().method() === method && new URL(response.url()).pathname === path,
  );
}

test("F05: catálogo, resposta citada, like, checkout e conversão no painel", async ({ page }) => {
  const adminToken = process.env.E2E_ADMIN_TOKEN;
  if (!adminToken) throw new Error("Defina E2E_ADMIN_TOKEN com o token do gateway de teste.");

  await page.goto("/admin/metricas");
  const input = page.getByTestId("admin-token-input");
  const submit = page.getByTestId("admin-token-submit");
  const unauthorized = waitForResponse(page, "GET", METRICS_PATH);
  await input.fill("token-invalido-f05");
  await submit.click();
  expect((await unauthorized).status()).toBe(401);
  await expect(page.getByTestId("admin-error")).toBeVisible();

  const baseline = waitForResponse(page, "GET", METRICS_PATH);
  await input.fill(adminToken);
  await submit.click();
  const baselineResponse = await baseline;
  expect(baselineResponse.status()).toBe(200);
  const before = (await baselineResponse.json()) as MetricsSummary;
  await expect(page.getByTestId("admin-dashboard")).toBeVisible();

  const assistant = await openProduct(page, AIRFRYER_4L);
  const answer = await ask(assistant, "Posso usar formas de aluminio no cesto?");
  await expect(answerText(answer)).toContainText(/alumínio/i);
  await waitForDone(assistant);
  const citation = answer.locator('[data-testid^="citation-badge-"]').filter({ hasText: /p\.\s*14\b/ });
  await expect(citation).toContainText("Manual Airfryer SmartChef 4L");
  await citation.click();
  await expect(citation).toHaveAttribute("aria-expanded", "true");
  const excerpt = page.locator(`[id="${await citation.getAttribute("aria-controls")}"]`);
  await expect(excerpt).toContainText(/alumínio/i);

  const feedback = waitForResponse(page, "POST", FEEDBACK_PATH);
  await answer.locator('[data-testid^="feedback-like-"]').click();
  const feedbackResponse = await feedback;
  expect(feedbackResponse.status()).toBe(201);
  expect(feedbackResponse.request().postDataJSON()).toMatchObject({ rating: "LIKE" });
  await expect(answer.getByText("Obrigado pelo feedback!")).toBeVisible();

  const checkout = waitForResponse(page, "POST", CHECKOUT_PATH);
  await answer.getByTestId(`buy-now-btn-${AIRFRYER_4L}`).click();
  const checkoutResponse = await checkout;
  expect(checkoutResponse.status()).toBe(200);
  const liked = feedbackResponse.request().postDataJSON() as { session_id: string; message_id: string };
  expect(checkoutResponse.request().postDataJSON()).toMatchObject({
    sku: AIRFRYER_4L,
    session_id: liked.session_id,
    message_id: liked.message_id,
  });
  const confirmed = (await checkoutResponse.json()) as Checkout;
  expect(confirmed.status).toBe("CONFIRMED");
  await expect(page.getByTestId("checkout-confirmed")).toBeVisible();
  expect(confirmed.redirect_checkout_url).toMatch(/^https:\/\//);
  await expect(page.getByTestId("checkout-redirect-link")).toHaveAttribute(
    "href", confirmed.redirect_checkout_url,
  );

  const updated = waitForResponse(page, "GET", METRICS_PATH);
  await page.goto("/admin/metricas");
  const updatedResponse = await updated;
  expect(updatedResponse.status()).toBe(200);
  expect(new URL(updatedResponse.url()).searchParams.has("token")).toBe(false);
  const after = (await updatedResponse.json()) as MetricsSummary;
  expect(after.turns).toBe(before.turns + 1);
  expect(after.confirmed_checkouts).toBe(before.confirmed_checkouts + 1);
  expect(after.like_ratio).toBeGreaterThan(0);
  await expect(page.getByTestId("metric-confirmed-checkouts")).toContainText(
    after.confirmed_checkouts.toLocaleString("pt-BR"),
  );
  await expect(page.getByTestId("metric-turns")).toContainText(after.turns.toLocaleString("pt-BR"));
});

for (const [scenario, question] of [
  ["sem trechos relevantes", "Qual é a cotação do dólar hoje e o resultado do último jogo?"],
  ["sem resposta do modelo de teste", "Quem ganhou o último jogo do campeonato?"],
]) {
  test(`F05: recusa pergunta fora do domínio ${scenario}`, async ({ page }) => {
    const assistant = await openProduct(page, AIRFRYER_4L);
    const answer = await ask(assistant, question);
    await waitForDone(assistant);
    const refusal = answer.locator('[data-testid^="assistant-fallback-"]');
    await expect(refusal).toBeVisible();
    await expect(refusal).toContainText("LOW_SIMILARITY_FALLBACK");
    await expect(answerText(answer)).toHaveCount(0);
    await expect(answer.getByTestId("citation-list")).toHaveCount(0);
  });
}
