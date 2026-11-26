import assert from "node:assert/strict";
import test from "node:test";

import {
  SSEParser,
  SSEProtocolError,
  isStreamEventName,
} from "../src/domain/chat-events.js";

/**
 * @param {string} name
 * @param {unknown} payload
 * @returns {string}
 */
const frame = (name, payload) => `event: ${name}\ndata: ${JSON.stringify(payload)}\n\n`;

test("parses complete frames and keeps no state between events", () => {
  const parser = new SSEParser();
  const events = parser.feed(
    frame("metadata", {
      message_id: "m-1",
      session_id: "s-1",
      cache_hit: false,
      ttft_ms: 120,
    }) + frame("token", { delta: "Olá" })
  );
  assert.equal(events.length, 2);
  assert.deepEqual(events[0], {
    event: "metadata",
    data: { message_id: "m-1", session_id: "s-1", cache_hit: false, ttft_ms: 120 },
  });
  assert.deepEqual(events[1], { event: "token", data: { delta: "Olá" } });
});

test("handles frames split across arbitrary chunks, including a trailing CR", () => {
  const parser = new SSEParser();
  const body =
    "event: token\r\ndata: {\"delta\":\"a\"}\r\n\r\n" +
    "event: token\rdata: {\"delta\":\"b\"}\r\r" +
    "event: token\ndata: {\"delta\":\"c\"}\n\n";
  /** @type {string[]} */
  const deltas = [];
  for (let index = 0; index < body.length; index += 3) {
    for (const event of parser.feed(body.slice(index, index + 3))) {
      if (event.event === "token") deltas.push(event.data.delta);
    }
  }
  for (const event of parser.flush()) {
    if (event.event === "token") deltas.push(event.data.delta);
  }
  assert.deepEqual(deltas, ["a", "b", "c"]);
});

test("joins multi-line data and ignores comments", () => {
  const parser = new SSEParser();
  const events = parser.feed(
    ": keep-alive\n\n" +
      'event: citations\ndata: {"citations":\ndata: [{"chunk_id":"c1","sku":"SKU","manual_title":"Manual","page_number":2,"similarity_score":0.9,"excerpt":"trecho"}]}\n\n'
  );
  assert.equal(events.length, 1);
  assert.equal(events[0].event, "citations");
  if (events[0].event === "citations") {
    assert.equal(events[0].data.citations[0].chunk_id, "c1");
  }
});

test("flush dispatches a final frame without a blank line", () => {
  const parser = new SSEParser();
  const fed = parser.feed('event: done\ndata: {"finish_reason":"stop","total_latency_ms":1,"tokens_used":2}');
  assert.equal(fed.length, 0);
  const flushed = parser.flush();
  assert.equal(flushed.length, 1);
  assert.equal(flushed[0].event, "done");
});

test("rejects events outside the closed contract", () => {
  const parser = new SSEParser();
  assert.throws(
    () => parser.feed('event: openai\ndata: {"delta":"x"}\n\n'),
    SSEProtocolError
  );
  assert.equal(isStreamEventName("token"), true);
  assert.equal(isStreamEventName("openai"), false);
});

test("rejects malformed JSON and missing required fields", () => {
  const parser = new SSEParser();
  assert.throws(() => parser.feed("event: token\ndata: {oops}\n\n"), SSEProtocolError);
  assert.throws(() => parser.feed('event: token\ndata: {"text":"a"}\n\n'), SSEProtocolError);
  assert.throws(() => parser.feed('event: done\ndata: []\n\n'), SSEProtocolError);
});

test("ignores empty frames and returns protocol errors with the event name", () => {
  const parser = new SSEParser();
  assert.deepEqual(parser.feed("\n\n"), []);
  assert.throws(
    () => parser.feed('event: recommendations\ndata: {"items":[]}\n\n'),
    /recommendations/
  );
});
