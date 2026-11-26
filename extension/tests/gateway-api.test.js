import assert from "node:assert/strict";
import test from "node:test";

import {
  ApiError,
  StreamInterruptedError,
  createApiClient,
} from "../src/infrastructure/gateway-api.js";
import { uuid } from "./support/storage.js";

const SESSION_ID = uuid(1);
const REQUEST_ID = uuid(2);

const STREAM_BODY = [
  'event: metadata\ndata: {"message_id":"m-1","session_id":"s-1","cache_hit":false,"ttft_ms":120}\n\n',
  'event: token\ndata: {"delta":"Olá"}\n\n',
  'event: token\ndata: {"delta":" mundo"}\n\n',
  'event: recommendations\ndata: {"products":[{"sku":"AF-400-220V","name":"Airfryer","price":499.9,"stock_quantity":3,"voltage":"220V","image_url":"https://img.example/a.jpg","marketplace":"AMAZON","checkout_url":"https://amazon.example/a","recommendation_type":"PRIMARY","badge_label":"Ideal","justification":"x"}]}\n\n',
  'event: done\ndata: {"finish_reason":"stop","total_latency_ms":900,"tokens_used":12}\n\n',
].join("");

/**
 * @param {unknown} body
 * @param {{ status?: number, headers?: Record<string, string> }} [options]
 * @returns {Response}
 */
const jsonResponse = (body, options = {}) =>
  new Response(JSON.stringify(body), {
    status: options.status ?? 200,
    headers: { "Content-Type": "application/json", ...(options.headers ?? {}) },
  });

/**
 * @param {string} body
 * @param {number} [chunkSize]
 * @returns {Response}
 */
function sseResponse(body, chunkSize = 9) {
  const bytes = new TextEncoder().encode(body);
  const stream = new ReadableStream({
    start(controller) {
      for (let index = 0; index < bytes.length; index += chunkSize) {
        controller.enqueue(bytes.slice(index, index + chunkSize));
      }
      controller.close();
    },
  });
  return new Response(stream, {
    status: 200,
    headers: { "Content-Type": "text/event-stream" },
  });
}

/**
 * @param {number} status
 * @param {string} code
 * @param {string} message
 * @param {Record<string, string>} [headers]
 */
const errorResponse = (status, code, message, headers = {}) =>
  jsonResponse(
    { error: { code, message, trace_id: "trace-1", details: {} } },
    { status, headers }
  );

test("creates a session with the documented headers and body", async () => {
  /** @type {{ url: string, init: RequestInit }[]} */
  const calls = [];
  const client = createApiClient({
    baseUrl: "http://gateway.test:8000/",
    requestIdFactory: () => "req-1",
    fetchFn: async (url, init) => {
      calls.push({ url: String(url), init });
      return jsonResponse({
        session_id: SESSION_ID,
        restored: false,
        history: [],
        expires_in_seconds: 1800,
      });
    },
  });

  const snapshot = await client.createSession(REQUEST_ID);
  assert.equal(snapshot.session_id, SESSION_ID);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "http://gateway.test:8000/api/v1/sessions");
  assert.equal(calls[0].init.method, "POST");
  assert.deepEqual(JSON.parse(String(calls[0].init.body)), {
    session_id: REQUEST_ID,
  });
  const headers = new Headers(calls[0].init.headers);
  assert.equal(headers.get("Content-Type"), "application/json");
  assert.equal(headers.get("Accept"), "application/json");
  assert.equal(headers.get("X-Request-ID"), "req-1");
});

test("lists and fetches catalog products with encoded query/path", async () => {
  /** @type {string[]} */
  const urls = [];
  const client = createApiClient({
    baseUrl: "http://gateway.test",
    fetchFn: async (url) => {
      urls.push(String(url));
      if (String(url).includes("/products/")) {
        return jsonResponse({ sku: "AB/12", name: "Produto" });
      }
      return jsonResponse({ items: [], page: 1, page_size: 8, total: 0 });
    },
  });
  await client.listProducts({ q: "Airfryer 4L", voltage: "220V", pageSize: 8 });
  await client.getProduct("AB/12");
  assert.ok(urls[0].includes("q=Airfryer+4L"));
  assert.ok(urls[0].includes("voltage=220V"));
  assert.ok(urls[0].includes("page_size=8"));
  assert.ok(urls[1].endsWith("/api/v1/products/AB%2F12"));
});

test("maps the REST error envelope and Retry-After", async () => {
  const client = createApiClient({
    baseUrl: "http://gateway.test",
    fetchFn: async () => errorResponse(429, "RATE_LIMITED", "Limite excedido.", { "Retry-After": "7" }),
  });
  await assert.rejects(
    () => client.createSession(),
    (error) =>
      error instanceof ApiError &&
      error.status === 429 &&
      error.code === "RATE_LIMITED" &&
      error.message === "Limite excedido." &&
      error.retryAfterSeconds === 7
  );
});

test("turns network failures into a typed ApiError", async () => {
  const client = createApiClient({
    baseUrl: "http://gateway.test",
    fetchFn: async () => {
      throw new TypeError("fetch failed");
    },
  });
  await assert.rejects(
    () => client.health(),
    (error) =>
      error instanceof ApiError &&
      error.status === 0 &&
      error.code === "NETWORK_ERROR" &&
      /conectar/.test(error.message)
  );
});

test("streams validated SSE events from chunks split anywhere", async () => {
  const client = createApiClient({
    baseUrl: "http://gateway.test",
    fetchFn: async () => sseResponse(STREAM_BODY, 7),
  });
  /** @type {string[]} */
  const events = [];
  /** @type {string[]} */
  const deltas = [];
  for await (const event of client.streamChat({
    sessionId: SESSION_ID,
    clientRequestId: REQUEST_ID,
    message: "Pergunta",
  })) {
    events.push(event.event);
    if (event.event === "token") deltas.push(event.data.delta);
  }
  assert.deepEqual(events, ["metadata", "token", "token", "recommendations", "done"]);
  assert.deepEqual(deltas, ["Olá", " mundo"]);
});

test("rejects a stream that closes before done", async () => {
  const client = createApiClient({
    baseUrl: "http://gateway.test",
    fetchFn: async () =>
      sseResponse(
        'event: metadata\ndata: {"message_id":"m","session_id":"s","cache_hit":false,"ttft_ms":1}\n\n'
      ),
  });
  await assert.rejects(
    async () => {
      for await (const _event of client.streamChat({
        sessionId: SESSION_ID,
        clientRequestId: REQUEST_ID,
        message: "Pergunta",
      })) {
        // consume
      }
    },
    StreamInterruptedError
  );
});

test("retries TURN_IN_PROGRESS with the same client_request_id and Retry-After", async () => {
  /** @type {{ body: string, header: string | null }[]} */
  const requests = [];
  let attempts = 0;
  /** @type {number[]} */
  const waits = [];
  const client = createApiClient({
    baseUrl: "http://gateway.test",
    requestIdFactory: () => `request-${requests.length + 1}`,
    wait: async (milliseconds) => {
      waits.push(milliseconds);
    },
    fetchFn: async (_url, init) => {
      attempts += 1;
      const headers = new Headers(init?.headers);
      requests.push({
        body: String(init?.body),
        header: headers.get("X-Request-ID"),
      });
      if (attempts === 1) {
        return errorResponse(409, "TURN_IN_PROGRESS", "Em andamento.", {
          "Retry-After": "2",
        });
      }
      return sseResponse(STREAM_BODY);
    },
  });

  for await (const _event of client.streamChat({
    sessionId: SESSION_ID,
    clientRequestId: REQUEST_ID,
    message: "Pergunta",
  })) {
    // consume
  }
  assert.deepEqual(waits, [2000]);
  assert.equal(attempts, 2);
  assert.equal(JSON.parse(requests[0].body).client_request_id, REQUEST_ID);
  assert.equal(JSON.parse(requests[1].body).client_request_id, REQUEST_ID);
  assert.notEqual(requests[0].header, requests[1].header);
});

test("sends context filters only when present", async () => {
  /** @type {unknown[]} */
  const bodies = [];
  const client = createApiClient({
    baseUrl: "http://gateway.test",
    fetchFn: async (_url, init) => {
      bodies.push(JSON.parse(String(init?.body)));
      return sseResponse(STREAM_BODY);
    },
  });
  for await (const _event of client.streamChat({
    sessionId: SESSION_ID,
    clientRequestId: REQUEST_ID,
    message: "Pergunta",
    contextFilters: { current_product_sku: "AF-400-220V", preferred_voltage: "220V" },
  })) {
    // consume
  }
  assert.deepEqual(bodies[0].context_filters, {
    current_product_sku: "AF-400-220V",
    preferred_voltage: "220V",
  });

  bodies.length = 0;
  for await (const _event of client.streamChat({
    sessionId: SESSION_ID,
    clientRequestId: REQUEST_ID,
    message: "Pergunta",
    contextFilters: {},
  })) {
    // consume
  }
  assert.equal(Object.hasOwn(bodies[0], "context_filters"), false);
});

test("returns CONFIRMED and Conflict from the mock checkout", async () => {
  const confirmed = {
    checkout_event_id: uuid(3),
    status: "CONFIRMED",
    sku: "AF-400-220V",
    product_name: "Airfryer",
    voltage: "220V",
    marketplace: "AMAZON",
    redirect_checkout_url: "https://amazon.example/a",
    quantity: 1,
    confirmed_unit_price: 499.9,
    total_amount: 499.9,
    remaining_stock: 2,
    message: "ok",
  };
  const conflict = {
    checkout_event_id: uuid(4),
    status: "PRICE_CHANGED",
    sku: "AF-400-220V",
    current_price: 529.9,
    current_stock: 3,
    redirect_checkout_url: null,
    message: "Preço mudou.",
  };
  let response = jsonResponse(confirmed);
  const client = createApiClient({
    baseUrl: "http://gateway.test",
    fetchFn: async () => response,
  });
  const body = {
    session_id: SESSION_ID,
    message_id: REQUEST_ID,
    sku: "AF-400-220V",
    recommendation_type: "PRIMARY",
    quantity: 1,
    displayed_price: 499.9,
  };
  assert.equal((await client.postCheckout(body)).status, "CONFIRMED");

  response = jsonResponse(conflict, { status: 409 });
  const answer = await client.postCheckout(body);
  assert.equal(answer.status, "PRICE_CHANGED");
  assert.equal(answer.current_price, 529.9);
});

test("a 409 that is not a Conflict shape becomes ApiError", async () => {
  const client = createApiClient({
    baseUrl: "http://gateway.test",
    fetchFn: async () => errorResponse(409, "IDEMPOTENCY_CONFLICT", "Conflito."),
  });
  await assert.rejects(
    () =>
      client.postCheckout({
        session_id: SESSION_ID,
        message_id: REQUEST_ID,
        sku: "AF-400-220V",
        recommendation_type: "PRIMARY",
        quantity: 1,
        displayed_price: 1,
      }),
    (error) => error instanceof ApiError && error.code === "IDEMPOTENCY_CONFLICT"
  );
});

test("posts feedback and reads health", async () => {
  /** @type {{ url: string, body: unknown }[]} */
  const calls = [];
  const client = createApiClient({
    baseUrl: "http://gateway.test",
    fetchFn: async (url, init) => {
      calls.push({ url: String(url), body: init?.body ? JSON.parse(String(init.body)) : null });
      if (String(url).endsWith("/feedback")) {
        return jsonResponse(
          { feedback_id: uuid(5), status: "RECORDED", recorded_at: "2026-01-01T00:00:00Z" },
          { status: 201 }
        );
      }
      return jsonResponse({ status: "ok", components: { redis: "ok" }, version: "1.0" });
    },
  });
  const recorded = await client.postFeedback({
    session_id: SESSION_ID,
    message_id: REQUEST_ID,
    rating: "LIKE",
  });
  assert.equal(recorded.status, "RECORDED");
  const health = await client.health();
  assert.equal(health.status, "ok");
  assert.deepEqual(calls[0].body, {
    session_id: SESSION_ID,
    message_id: REQUEST_ID,
    rating: "LIKE",
  });
});
