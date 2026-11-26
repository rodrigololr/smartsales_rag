import assert from "node:assert/strict";
import test from "node:test";

import {
  applyStreamEvent,
  buildFeedbackPayload,
  canBuyFrom,
  canRate,
  createAssistantMessage,
  createRestoredAssistantMessage,
  createUserMessage,
  finishWithFailure,
} from "../src/domain/chat-state.js";

const metadata = {
  event: "metadata",
  data: { message_id: "m-1", session_id: "s-1", cache_hit: true, ttft_ms: 321 },
};
const token = { event: "token", data: { delta: "Olá" } };
const done = {
  event: "done",
  data: { finish_reason: "stop", total_latency_ms: 900, tokens_used: 12 },
};
const card = {
  sku: "AF-400-220V",
  name: "Airfryer 4L",
  price: 499.9,
  stock_quantity: 4,
  voltage: "220V",
  image_url: "https://cdn.example/a.jpg",
  marketplace: "AMAZON",
  checkout_url: "https://amazon.example/a",
  recommendation_type: "PRIMARY",
  badge_label: "Ideal",
  justification: "Consulta",
};

test("creates user and assistant messages with the contract defaults", () => {
  const user = createUserMessage("u-1", "Pergunta");
  assert.equal(user.role, "user");
  assert.equal(user.content, "Pergunta");
  assert.equal(user.isStreaming, false);
  assert.deepEqual(user.citations, []);

  const assistant = createAssistantMessage("a-1");
  assert.equal(assistant.role, "assistant");
  assert.equal(assistant.isStreaming, true);
  assert.equal(assistant.serverMessageId, null);
  assert.equal(assistant.errorCode, null);

  const restored = createRestoredAssistantMessage("a-2", "Resposta antiga");
  assert.equal(restored.isStreaming, false);
  assert.equal(restored.content, "Resposta antiga");
});

test("applies metadata, tokens, citations and recommendations immutably", () => {
  const initial = createAssistantMessage("a-1");
  const withMetadata = applyStreamEvent(initial, metadata);
  assert.equal(initial.serverMessageId, null, "original message is not mutated");
  assert.equal(withMetadata.serverMessageId, "m-1");
  assert.equal(withMetadata.ttftMs, 321);
  assert.equal(withMetadata.cacheHit, true);

  const withToken = applyStreamEvent(withMetadata, token);
  assert.equal(withToken.content, "Olá");
  const withSecondToken = applyStreamEvent(withToken, { event: "token", data: { delta: "!" } });
  assert.equal(withSecondToken.content, "Olá!");

  const withCitations = applyStreamEvent(withSecondToken, {
    event: "citations",
    data: {
      citations: [
        {
          chunk_id: "c-1",
          sku: "AF-400-220V",
          manual_title: "Manual",
          page_number: 14,
          similarity_score: 0.9,
          excerpt: "Trecho",
        },
      ],
    },
  });
  assert.equal(withCitations.citations.length, 1);

  const withCards = applyStreamEvent(withCitations, {
    event: "recommendations",
    data: { products: [card] },
  });
  assert.equal(withCards.recommendations[0].sku, "AF-400-220V");

  const finished = applyStreamEvent(withCards, done);
  assert.equal(finished.isStreaming, false);
});

test("correction replaces the content and marks the bubble", () => {
  const message = applyStreamEvent(createAssistantMessage("a-1"), token);
  const corrected = applyStreamEvent(message, {
    event: "correction",
    data: { violation_code: "STREAM_INTERRUPTED", content: "Resposta segura." },
  });
  assert.equal(corrected.content, "Resposta segura.");
  assert.equal(corrected.wasCorrected, true);
});

test("error discards every partial artifact and keeps later recommendations", () => {
  let message = applyStreamEvent(createAssistantMessage("a-1"), metadata);
  message = applyStreamEvent(message, token);
  message = applyStreamEvent(message, {
    event: "citations",
    data: {
      citations: [
        {
          chunk_id: "c-1",
          sku: "AF",
          manual_title: "Manual",
          page_number: 1,
          similarity_score: 0.8,
          excerpt: "x",
        },
      ],
    },
  });
  message = applyStreamEvent(message, { event: "recommendations", data: { products: [card] } });

  const fallback = applyStreamEvent(message, {
    event: "error",
    data: {
      code: "LOW_SIMILARITY_FALLBACK",
      recoverable: true,
      fallback_message: "A especificação não consta no manual.",
    },
  });
  assert.equal(fallback.content, "");
  assert.deepEqual(fallback.citations, []);
  assert.deepEqual(fallback.recommendations, []);
  assert.equal(fallback.errorCode, "LOW_SIMILARITY_FALLBACK");
  assert.equal(fallback.errorFallback, "A especificação não consta no manual.");
  assert.equal(fallback.wasCorrected, false);

  const withCards = applyStreamEvent(fallback, {
    event: "recommendations",
    data: { products: [card] },
  });
  assert.equal(withCards.recommendations.length, 1);
  assert.equal(withCards.errorCode, "LOW_SIMILARITY_FALLBACK");
});

test("terminal failure clears partial content and allows retry-rating rules", () => {
  let message = applyStreamEvent(createAssistantMessage("a-1"), metadata);
  message = applyStreamEvent(message, token);
  message = applyStreamEvent(message, { event: "recommendations", data: { products: [card] } });
  const failed = finishWithFailure(message, {
    errorCode: "LLM_UNAVAILABLE",
    errorFallback: "Caiu a conexão.",
  });
  assert.equal(failed.content, "");
  assert.deepEqual(failed.recommendations, []);
  assert.equal(failed.isStreaming, false);
  assert.equal(failed.errorCode, "LLM_UNAVAILABLE");
  assert.equal(canRate(failed), false);
  assert.equal(canBuyFrom(failed), false);
});

test("canRate and canBuyFrom require a finished server message", () => {
  const base = createAssistantMessage("a-1");
  const streaming = applyStreamEvent(base, metadata);
  assert.equal(canRate(streaming), false);
  assert.equal(canBuyFrom(streaming), false);

  const finished = applyStreamEvent(
    applyStreamEvent(streaming, token),
    done
  );
  assert.equal(canRate(finished), true);
  assert.equal(canBuyFrom(finished), false);

  const withCard = applyStreamEvent(finished, {
    event: "recommendations",
    data: { products: [card] },
  });
  assert.equal(canBuyFrom(withCard), true);

  const withoutServerId = { ...withCard, serverMessageId: null };
  assert.equal(canRate(withoutServerId), false);
  assert.equal(canBuyFrom(withoutServerId), false);
});

test("feedback payload requires a dislike reason", () => {
  assert.deepEqual(
    buildFeedbackPayload("s-1", "m-1", "LIKE"),
    { session_id: "s-1", message_id: "m-1", rating: "LIKE" }
  );
  assert.deepEqual(
    buildFeedbackPayload("s-1", "m-1", "DISLIKE", "WRONG_VOLTAGE"),
    {
      session_id: "s-1",
      message_id: "m-1",
      rating: "DISLIKE",
      reason_category: "WRONG_VOLTAGE",
    }
  );
  assert.throws(() => buildFeedbackPayload("s-1", "m-1", "DISLIKE"), /reason_category/);
  assert.throws(() => buildFeedbackPayload("", "m-1", "LIKE"), /session_id/);
});
