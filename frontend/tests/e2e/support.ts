import { expect, type Locator, type Page } from "@playwright/test";

export const AIRFRYER_4L = "AF-400-220V";
export const AIRFRYER_55L = "AF-550-220V";
export const SILICONE_KIT = "KIT-SIL-01";

/** Teto de SLA em homologação (CLAUDE.md, regra 6): TTFT <= 2,0 s. */
export const TTFT_LIMIT_MS = Number(process.env.E2E_TTFT_LIMIT_MS ?? 2000);
/** Cache hit (E2E-06): resposta em menos de 200 ms. */
export const CACHE_HIT_LIMIT_MS = 200;

/** Abre o produto pela vitrine e devolve o painel do Consultor IA visível. */
export async function openProduct(page: Page, sku: string): Promise<Locator> {
  await page.goto("/");
  await page.getByTestId(`product-card-${sku}`).click();
  await expect(page).toHaveURL(new RegExp(`/produto/${sku}$`));
  const assistant = page
    .locator(`[data-testid="product-assistant"][data-sku="${sku}"]`)
    .filter({ visible: true })
    .first();
  await expect(assistant).toBeVisible();
  return assistant;
}

/** Envia a pergunta e devolve a bolha da resposta que ela abriu. */
export async function ask(assistant: Locator, question: string): Promise<Locator> {
  const answers = assistant.locator('[data-testid^="assistant-message-"]');
  const before = await answers.count();
  await assistant.getByTestId("chat-prompt-input").fill(question);
  await assistant.getByTestId("chat-prompt-input").press("Enter");
  await expect(answers).toHaveCount(before + 1);
  return answers.nth(before);
}

/** Espera o turno terminar: o campo de pergunta volta a ficar habilitado no `done`. */
export async function waitForDone(assistant: Locator): Promise<void> {
  await expect(assistant.getByTestId("chat-prompt-input")).toBeEnabled({ timeout: 30_000 });
}

/** TTFT do servidor exibido na bolha ("TTFT 890 ms"). */
export async function shownTtftMs(answer: Locator): Promise<number> {
  const label = answer.getByText(/TTFT \d+ ms/);
  await expect(label).toBeVisible();
  const match = /TTFT (\d+) ms/.exec((await label.textContent()) ?? "");
  if (!match) throw new Error("TTFT não exibido na resposta");
  return Number(match[1]);
}
