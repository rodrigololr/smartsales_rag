import assert from "node:assert/strict";
import test from "node:test";

import {
  ChatSessionController,
  buildContextFilters,
  describeTransportFailure,
} from "../src/application/chat-session.js";
import {
  ApiError,
  StreamInterruptedError,
} from "../src/infrastructure/gateway-api.js";
import { DEFAULT_SETTINGS } from "../src/infrastructure/settings.js";
import { uuid } from "./support/storage.js";

const SETTINGS = { ...DEFAULT_SETTINGS, apiBaseUrl: "http://gateway.test" };

const metadata = (messageId, overrides = {}) => ({
  event: "metadata",
  data: {
    message_id: messageId,
    session_id: uuid(99),
    cache_hit: false,
    ttft_ms: 100,
    ...overrides,
  },
});
const token = (delta) => ({ event: "token", data: { delta } });
const done = (reason = "stop") => ({
  event: "done",
  data: { finish_reason: reason, total_latency_ms: 900, tokens_used: 10 },
});
const card = {
  sku: "AF-400-220V",
  name: "Airfryer 4L",
  price: 499.9,
  stock_quantity: 4,
  voltage: "220V",
  image_url: "https://img.example/a.jpg",
  marketplace: "AMAZON",
  checkout_url: "https://amazon.example/a",
  recommendation_type: "PRIMARY",
  badge_label: "Ideal",
  justification: "Consulta",
};

/**
 * @param {unknown} value
 * @returns {AsyncGenerator<any>}
 */
function scenario(value) {
  return (async function* () {
    if (value instanceof Error) throw value;
    for (const event of /** @type {any[]} */ (value)) yield event;
  })();
}

/**
 * @param {Partial<{ createSession: (sessionId: string | null, call: number) => any, streamChat: (input: any, call: number) => AsyncGenerator<any>, postFeedback: (payload: any) => any }>} [overrides]
 */
function makeApi(overrides = {}) {
  const calls = {
    createSession: [],
    deleteSession: [],
    streamChat: [],
    postFeedback: [],
    getProduct: [],
    listProducts: [],
  };
  let created = 0;
  return {
    calls,
    async createSession(sessionId = null) {
      calls.createSession.push(sessionId);
      if (overrides.createSession) {
        return overrides.createSession(sessionId, calls.createSession.length);
      }
      created += 1;
      return {
        session_id: uuid(100 + created),
        restored: false,
        history: [],
        expires_in_seconds: 1800,
      };
    },
    async deleteSession(sessionId) {
      calls.deleteSession.push(sessionId);
    },
    streamChat(input) {
      calls.streamChat.push(input);
      if (overrides.streamChat) return overrides.streamChat(input, calls.streamChat.length);
      return scenario([metadata("m-default"), token("ok"), done()]);
    },
    async postFeedback(payload) {
      calls.postFeedback.push(payload);
      if (overrides.postFeedback) return overrides.postFeedback(payload);
      return { feedback_id: uuid(500), status: "RECORDED", recorded_at: "2026-01-01T00:00:00Z" };
    },
    async getProduct(sku) {
      calls.getProduct.push(sku);
      throw new ApiError(404, "PRODUCT_NOT_FOUND", "not found");
    },
    async listProducts(query) {
      calls.listProducts.push(query);
      return { items: [], page: 1, page_size: 8, total: 0 };
    },
  };
}

/**
 * @param {string | null} [stored]
 */
function makeSessions(stored = null) {
  let current = stored;
  const calls = [];
  return {
    calls,
    current: () => current,
    async getSessionId() {
      calls.push("get");
      return current;
    },
    async setSessionId(sessionId) {
      calls.push(["set", sessionId]);
      current = sessionId;
    },
    async clearSessionId() {
      calls.push("clear");
      current = null;
    },
  };
}

/**
 * @param {{ api: ReturnType<typeof makeApi>, sessions: ReturnType<typeof makeSessions>, settings?: any, onChange?: (state: any) => void }} input
 */
function makeController({ api, sessions, settings = SETTINGS, onChange = () => {} }) {
  let id = 0;
  return new ChatSessionController({
    api,
    sessions,
    getSettings: () => settings,
    createId: () => `local-${++id}`,
    onChange,
    logger: { warn() {} },
  });
}

const PRODUCT_CONTEXT = {
  product: {
    sku: "AF-400-220V",
    name: "Airfryer 4L",
    price: 499.9,
    stock_quantity: 4,
    voltage: "220V",
    capacity_liters: 4,
    power_watts: 1500,
    image_url: "",
    marketplace: "AMAZON",
    checkout_url: "",
    category: "Eletroportáteis",
    subcategory: "Fritadeiras Elétricas",
    brand: "Mondial",
    specs_json: {},
    updated_at: "2026-01-01T00:00:00Z",
  },
  detection: null,
  resolvedBy: "sku",
};

test("builds context filters only with contract-valid values", () => {
  assert.deepEqual(
    buildContextFilters(
      { ...SETTINGS, preferredVoltage: "220V", budgetMax: 600.456 },
      { sku: "AF-400-220V" }
    ),
    {
      current_product_sku: "AF-400-220V",
      preferred_voltage: "220V",
      budget_max: 600.46,
    }
  );
  assert.equal(buildContextFilters({ ...SETTINGS, budgetMax: null }, null), undefined);
});

test("maps transport failures to safe fallbacks", () => {
  assert.equal(describeTransportFailure(new StreamInterruptedError()).errorCode, "LLM_UNAVAILABLE");
  assert.match(
    describeTransportFailure(new ApiError(429, "RATE_LIMITED", "x")).errorFallback,
    /Muitas perguntas/
  );
  assert.match(
    describeTransportFailure(new ApiError(0, "NETWORK_ERROR", "x")).errorFallback,
    /conectar/
  );
  assert.equal(describeTransportFailure(new Error("boom")).errorCode, "INTERNAL_ERROR");
});

test("restores the gateway session window when reopened", async () => {
  const sessions = makeSessions(uuid(1));
  const api = makeApi({
    createSession: () => ({
      session_id: uuid(1),
      restored: true,
      history: [
        { id: "h-1", role: "user", content: "Oi" },
        { id: "h-2", role: "assistant", content: "Olá" },
      ],
      expires_in_seconds: 1800,
    }),
  });
  const controller = makeController({ api, sessions });
  const state = await controller.initialize();
  assert.equal(state.sessionId, uuid(1));
  assert.equal(state.restored, true);
  assert.equal(state.messages.length, 2);
  assert.equal(state.messages[1].serverMessageId, "h-2");
  assert.equal(state.messages[1].isStreaming, false);
  assert.equal(sessions.current(), uuid(1));
});

test("an expired stored session is replaced with a fresh one and a notice", async () => {
  const sessions = makeSessions(uuid(1));
  const api = makeApi({
    createSession: () => ({
      session_id: uuid(2),
      restored: false,
      history: [],
      expires_in_seconds: 1800,
    }),
  });
  const controller = makeController({ api, sessions });
  const state = await controller.initialize();
  assert.equal(state.sessionId, uuid(2));
  assert.equal(state.messages.length, 0);
  assert.match(state.notice, /expirou/);
  assert.equal(sessions.current(), uuid(2));
});

test("an offline restore keeps the stored id so the next turn can reveal the real state", async () => {
  const sessions = makeSessions(uuid(1));
  const api = makeApi({
    createSession: () => {
      throw new ApiError(0, "NETWORK_ERROR", "offline");
    },
  });
  const controller = makeController({ api, sessions });
  const state = await controller.initialize();
  assert.equal(state.sessionId, uuid(1));
  assert.equal(state.messages.length, 0);
});

test("send creates the session lazily and applies the stream to the assistant turn", async () => {
  const sessions = makeSessions();
  const settings = { ...SETTINGS, preferredVoltage: "220V", budgetMax: 600.5 };
  const api = makeApi({
    streamChat: () =>
      scenario([
        metadata("m-1", { cache_hit: true, ttft_ms: 321 }),
        token("Olá"),
        { event: "recommendations", data: { products: [card] } },
        done(),
      ]),
  });
  /** @type {any[]} */
  const states = [];
  const controller = makeController({
    api,
    sessions,
    settings,
    onChange: (state) => states.push(state),
  });
  controller.setContext(PRODUCT_CONTEXT);
  await controller.send("  Pergunta  ");

  assert.deepEqual(api.calls.createSession, [null]);
  assert.equal(api.calls.streamChat.length, 1);
  const input = api.calls.streamChat[0];
  assert.equal(input.sessionId, uuid(101));
  assert.equal(input.message, "Pergunta");
  assert.match(input.clientRequestId, /^local-/);
  assert.deepEqual(input.contextFilters, {
    current_product_sku: "AF-400-220V",
    preferred_voltage: "220V",
    budget_max: 600.5,
  });
  assert.equal(sessions.current(), uuid(101));

  const state = controller.getState();
  assert.equal(state.isStreaming, false);
  assert.equal(state.messages.length, 2);
  assert.equal(state.messages[0].content, "Pergunta");
  const assistant = state.messages[1];
  assert.equal(assistant.content, "Olá");
  assert.equal(assistant.serverMessageId, "m-1");
  assert.equal(assistant.cacheHit, true);
  assert.equal(assistant.ttftMs, 321);
  assert.equal(assistant.recommendations[0].sku, "AF-400-220V");
  assert.equal(assistant.isStreaming, false);
  assert.equal(states.at(-1).isStreaming, false);
});

test("the SSE error event discards partial text but keeps fallback cards", async () => {
  const sessions = makeSessions();
  const api = makeApi({
    streamChat: () =>
      scenario([
        metadata("m-1"),
        token("Texto parcial"),
        {
          event: "error",
          data: {
            code: "LOW_SIMILARITY_FALLBACK",
            recoverable: true,
            fallback_message: "A especificação não consta no manual.",
          },
        },
        { event: "recommendations", data: { products: [card] } },
        done("fallback"),
      ]),
  });
  const controller = makeController({ api, sessions });
  await controller.send("Pergunta");
  const assistant = controller.getState().messages.at(-1);
  assert.equal(assistant.content, "");
  assert.equal(assistant.citations.length, 0);
  assert.equal(assistant.recommendations.length, 1);
  assert.equal(assistant.errorCode, "LOW_SIMILARITY_FALLBACK");
  assert.equal(assistant.errorFallback, "A especificação não consta no manual.");
  assert.equal(assistant.isStreaming, false);
});

test("an interrupted stream reconnects once with the same client_request_id", async () => {
  const sessions = makeSessions();
  const api = makeApi({
    streamChat: (_input, call) => {
      if (call === 1) {
        return (async function* () {
          yield metadata("m-partial");
          yield token("Parcial");
          throw new StreamInterruptedError();
        })();
      }
      return scenario([metadata("m-final"), token("Resposta completa"), done()]);
    },
  });
  const controller = makeController({ api, sessions });
  await controller.send("Pergunta");

  assert.equal(api.calls.streamChat.length, 2);
  assert.equal(
    api.calls.streamChat[0].clientRequestId,
    api.calls.streamChat[1].clientRequestId
  );
  const assistant = controller.getState().messages.at(-1);
  assert.equal(assistant.content, "Resposta completa");
  assert.equal(assistant.serverMessageId, "m-final");
  assert.equal(assistant.errorCode, null);
});

test("manual retry of a persistently interrupted turn reuses its request id", async () => {
  const sessions = makeSessions();
  const api = makeApi({
    streamChat: (_input, call) => {
      if (call <= 2) {
        return (async function* () {
          yield metadata(`m-${call}`);
          throw new StreamInterruptedError();
        })();
      }
      return scenario([metadata("m-ok"), token("Agora foi"), done()]);
    },
  });
  const controller = makeController({ api, sessions });
  await controller.send("Pergunta");
  const assistant = controller.getState().messages.at(-1);
  assert.equal(assistant.errorCode, "LLM_UNAVAILABLE");
  assert.equal(api.calls.streamChat.length, 2);
  const originalRequestId = api.calls.streamChat[0].clientRequestId;

  await controller.retry(assistant.id);
  assert.equal(api.calls.streamChat.length, 3);
  assert.equal(api.calls.streamChat[2].clientRequestId, originalRequestId);
  assert.equal(controller.getState().messages.at(-1).content, "Agora foi");
  assert.equal(controller.getState().messages.at(-1).errorCode, null);
});

test("an expired session between turns is recreated and the turn retried once", async () => {
  const sessions = makeSessions(uuid(1));
  const api = makeApi({
    createSession: (_sessionId, call) => ({
      session_id: call === 1 ? uuid(1) : uuid(2),
      restored: call === 1,
      history: [],
      expires_in_seconds: 1800,
    }),
    streamChat: (_input, call) => {
      if (call === 1) {
        return scenario(new ApiError(404, "SESSION_NOT_FOUND", "expired"));
      }
      return scenario([metadata("m-ok"), token("Nova sessão"), done()]);
    },
  });
  const controller = makeController({ api, sessions });
  await controller.initialize();
  await controller.send("Pergunta");

  assert.deepEqual(api.calls.createSession, [uuid(1), null]);
  assert.equal(api.calls.streamChat.length, 2);
  assert.notEqual(
    api.calls.streamChat[0].clientRequestId,
    api.calls.streamChat[1].clientRequestId
  );
  assert.match(controller.getState().notice, /expirou/);
  assert.equal(controller.getState().sessionId, uuid(2));
  assert.equal(controller.getState().messages.at(-1).content, "Nova sessão");
  assert.equal(sessions.current(), uuid(2));
});

test("terminal API errors become a safe fallback with a retryable code", async () => {
  const sessions = makeSessions();
  const api = makeApi({
    streamChat: () => scenario(new ApiError(429, "RATE_LIMITED", "Muitas requisições.")),
  });
  const controller = makeController({ api, sessions });
  await controller.send("Pergunta");
  const assistant = controller.getState().messages.at(-1);
  assert.equal(assistant.isStreaming, false);
  assert.equal(assistant.content, "");
  assert.equal(assistant.errorCode, "INTERNAL_ERROR");
  assert.match(assistant.errorFallback, /Muitas perguntas/);
});

test("reset aborts the turn, deletes the gateway session and clears local state", async () => {
  const sessions = makeSessions();
  const api = makeApi();
  const controller = makeController({ api, sessions });
  await controller.send("Pergunta");
  const sessionId = controller.getState().sessionId;
  await controller.reset();
  assert.deepEqual(api.calls.deleteSession, [sessionId]);
  assert.equal(sessions.current(), null);
  assert.equal(controller.getState().messages.length, 0);
  assert.equal(controller.getState().sessionId, null);
  assert.equal(controller.getState().isStreaming, false);
});

test("feedback is linked to the server message and tolerates the 409 already-recorded answer", async () => {
  const sessions = makeSessions();
  let rejectAlreadyRecorded = false;
  const api = makeApi({
    postFeedback: () => {
      if (rejectAlreadyRecorded) {
        throw new ApiError(409, "FEEDBACK_ALREADY_RECORDED", "Já avaliada.");
      }
      return { feedback_id: uuid(500), status: "RECORDED", recorded_at: "2026-01-01T00:00:00Z" };
    },
  });
  const controller = makeController({ api, sessions });
  await controller.send("Pergunta");
  const assistantId = controller.getState().messages.at(-1).id;
  await controller.submitFeedback(assistantId, "LIKE");
  assert.deepEqual(api.calls.postFeedback[0], {
    session_id: controller.getState().sessionId,
    message_id: "m-default",
    rating: "LIKE",
  });
  assert.equal(controller.getState().messages.at(-1).feedback, "LIKE");

  rejectAlreadyRecorded = true;
  await controller.submitFeedback(assistantId, "DISLIKE", "WRONG_VOLTAGE");
  assert.equal(controller.getState().messages.at(-1).feedbackAlreadyRecorded, true);
});

test("feedback without a server message id is rejected", async () => {
  const controller = makeController({ api: makeApi(), sessions: makeSessions() });
  await assert.rejects(
    () => controller.submitFeedback("missing", "LIKE"),
    /message_id do servidor/
  );
});

test("patchProduct updates every card of the same SKU with validated SQL values", async () => {
  const sessions = makeSessions();
  const api = makeApi({
    streamChat: () =>
      scenario([
        metadata("m-1"),
        token("Veja"),
        { event: "recommendations", data: { products: [card, { ...card }] } },
        done(),
      ]),
  });
  const controller = makeController({ api, sessions });
  await controller.send("Pergunta");
  controller.patchProduct("AF-400-220V", { price: 599.9, stock_quantity: 0 });
  const cards = controller.getState().messages.at(-1).recommendations;
  assert.equal(cards.length, 2);
  assert.equal(cards[0].price, 599.9);
  assert.equal(cards[0].stock_quantity, 0);
  assert.equal(cards[1].stock_quantity, 0);
});
