import assert from "node:assert/strict";
import test from "node:test";

import {
  fallbackInfo,
  formatBRL,
  hostOf,
  marketplaceLabel,
  recommendationLabel,
  safeHttpUrl,
  voltageLabel,
  voltageTone,
} from "../src/ui/format.js";

const plain = (value) => value.replace(/\u00a0/g, " ");

test("formats Brazilian currency and marketplace names", () => {
  assert.equal(plain(formatBRL(1234.5)), "R$ 1.234,50");
  assert.equal(marketplaceLabel("AMAZON"), "Amazon");
  assert.equal(marketplaceLabel("MERCADO_LIVRE"), "Mercado Livre");
  assert.equal(marketplaceLabel("SHOPEE"), "Shopee");
  assert.equal(marketplaceLabel("LOJA_OFICIAL"), "Loja Oficial");
  assert.equal(marketplaceLabel("UNKNOWN"), "Loja Oficial");
});

test("labels voltage and recommendation types", () => {
  assert.equal(voltageLabel("BIVOLT"), "Bivolt");
  assert.equal(voltageLabel("220V"), "220V");
  assert.equal(voltageLabel("N/A"), "Não se aplica");
  assert.equal(voltageTone("220V"), "220v");
  assert.equal(voltageTone("127V"), "127v");
  assert.equal(voltageTone("BIVOLT"), "bivolt");
  assert.equal(voltageTone("N/A"), "na");
  assert.equal(recommendationLabel("PRIMARY"), "Recomendado");
  assert.equal(recommendationLabel("UPSELL"), "Upgrade");
  assert.equal(recommendationLabel("CROSS_SELL"), "Combina");
  assert.equal(recommendationLabel("OPTION"), "Opção");
});

test("maps fallback codes to user-facing titles", () => {
  assert.equal(fallbackInfo("LOW_SIMILARITY_FALLBACK").retryable, false);
  assert.equal(fallbackInfo("GUARDRAIL_BLOCKED").title, "Pergunta fora do escopo do consultor");
  assert.equal(fallbackInfo("LLM_UNAVAILABLE").retryable, true);
  assert.equal(fallbackInfo(null).title, "Não foi possível concluir a resposta");
});

test("only exposes http(s) URLs and a readable host", () => {
  assert.equal(safeHttpUrl("https://example.com/a"), "https://example.com/a");
  assert.equal(safeHttpUrl("http://example.com/a"), "http://example.com/a");
  assert.equal(safeHttpUrl("javascript:alert(1)"), null);
  assert.equal(safeHttpUrl("data:text/html,x"), null);
  assert.equal(safeHttpUrl("not a url"), null);
  assert.equal(safeHttpUrl(null), null);
  assert.equal(hostOf("https://example.com:8443/a"), "example.com:8443");
  assert.equal(hostOf("broken"), "broken");
});
