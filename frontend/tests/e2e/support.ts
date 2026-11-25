import { expect, type Locator, type Page } from "@playwright/test";

export const AIRFRYER_4L = "AF-400-220V";
export const AIRFRYER_55L = "AF-550-220V";
export const SILICONE_KIT = "KIT-SIL-01";

export const CHAT_STREAM_PATH = "/api/v1/chat/stream";
export const SESSIONS_PATH = "/api/v1/sessions";
export const FEEDBACK_PATH = "/api/v1/feedback";
export const CHECKOUT_PATH = "/api/v1/checkout/mock";
/**
 * Teto folgado para o primeiro texto aparecer: só detecta resposta travada.
 * O SLA de TTFT (p95) é aferido por `python -m app.telemetry.sla_probe`, não aqui.
 */
export const FIRST_TEXT_SMOKE_LIMIT_MS = 15_000;
/** Cache hit (E2E-06): resposta em menos de 200 ms. */
export const CACHE_HIT_LIMIT_MS = 200;

/**
 * Abre o produto pela vitrine e devolve o painel do Consultor IA visível. Abaixo de `lg`
 * o painel não fica docado: o botão flutuante abre a *sheet*.
 */
export async function openProduct(page: Page, sku: string): Promise<Locator> {
  await page.goto("/");
  await page.getByTestId(`product-card-${sku}`).click();
  await expect(page).toHaveURL(new RegExp(`/produto/${sku}$`));
  const assistant = page
    .locator(`[data-testid="product-assistant"][data-sku="${sku}"]`)
    .filter({ visible: true })
    .first();
  const openAssistant = page.getByTestId("open-assistant-btn");
  if (await openAssistant.isVisible()) {
    // Retried: a click that lands before hydration does nothing.
    await expect(async () => {
      await openAssistant.click();
      await expect(assistant).toBeVisible({ timeout: 2_000 });
    }).toPass();
  }
  await expect(assistant).toBeVisible();
  return assistant;
}

/** Texto da resposta dentro da bolha (ausente em turnos de fallback). */
export function answerText(answer: Locator): Locator {
  return answer.getByTestId("assistant-text");
}

/**
 * Envia a pergunta e devolve a bolha da resposta que ela abriu. Exige a requisição
 * ao gateway: com a vitrine em modo mock o teste falha em vez de passar sem a pilha.
 */
export async function ask(assistant: Locator, question: string): Promise<Locator> {
  const answers = assistant.locator('[data-testid^="assistant-message-"]');
  const before = await answers.count();
  const sentToGateway = assistant
    .page()
    .waitForRequest((request) => request.url().endsWith(CHAT_STREAM_PATH));
  await assistant.getByTestId("chat-prompt-input").fill(question);
  await assistant.getByTestId("chat-prompt-input").press("Enter");
  await sentToGateway;
  await expect(answers).toHaveCount(before + 1);
  return answers.nth(before);
}

/** Espera o turno terminar: o histórico deixa de estar `aria-busy` no `done`. */
export async function waitForDone(assistant: Locator): Promise<void> {
  await expect(assistant.getByTestId("chat-log")).toHaveAttribute("aria-busy", "false", { timeout: 30_000 });
}

/** TTFT do servidor exibido na bolha ("TTFT 890 ms"). */
export async function shownTtftMs(answer: Locator): Promise<number> {
  const label = answer.getByText(/TTFT \d+ ms/);
  await expect(label).toBeVisible();
  const match = /TTFT (\d+) ms/.exec((await label.textContent()) ?? "");
  if (!match) throw new Error("TTFT não exibido na resposta");
  return Number(match[1]);
}
