import { afterEach, describe, expect, it, vi } from "vitest";
import {
  ChatApiError,
  StreamInterruptedError,
  createSession,
  streamChat,
} from "@/lib/chat-api";
import type { StreamEvent } from "@/types/chat";

const encoder = new TextEncoder();
const done = { finish_reason: "stop", total_latency_ms: 10, tokens_used: 3 };
const input = {
  sessionId: "11111111-1111-4111-8111-111111111111",
  clientRequestId: "22222222-2222-4222-8222-222222222222",
  message: "Qual a voltagem?",
  currentProductSku: "AF-400-220V",
};

const sseResponse = (chunks: (string | Uint8Array)[]): Response =>
  new Response(
    new ReadableStream<Uint8Array>({
      start(controller) {
        for (const chunk of chunks) {
          controller.enqueue(typeof chunk === "string" ? encoder.encode(chunk) : chunk);
        }
        controller.close();
      },
    }),
    { status: 200, headers: { "Content-Type": "text/event-stream" } }
  );

const errorResponse = (status: number, code: string, headers: Record<string, string> = {}) =>
  new Response(JSON.stringify({ error: { code, message: code, trace_id: "t", details: {} } }), {
    status,
    headers: { "Content-Type": "application/json", ...headers },
  });

const collect = async (events: AsyncIterable<StreamEvent>): Promise<StreamEvent[]> => {
  const collected: StreamEvent[] = [];
  for await (const event of events) collected.push(event);
  return collected;
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("chat-api", () => {
  it("creates the session for the current product", async () => {
    const fetchMock = vi.fn(async () =>
      Response.json({ session_id: input.sessionId, restored: false, history: [], expires_in_seconds: 1800 }, { status: 201 })
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(createSession("AF-400-220V")).resolves.toBe(input.sessionId);
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toMatch(/\/api\/v1\/sessions$/);
    expect(JSON.parse(String(init.body))).toEqual({ current_product_sku: "AF-400-220V" });
  });

  it("posts the ChatStreamRequest contract and decodes UTF-8 split across chunks", async () => {
    const accented = encoder.encode('event: token\ndata: {"delta":"voltagem é"}\n\n');
    const splitAt = accented.indexOf(0xc3) + 1; // middle of the two-byte "é"
    const fetchMock = vi.fn(async () =>
      sseResponse([
        accented.slice(0, splitAt),
        accented.slice(splitAt),
        `event: done\ndata: ${JSON.stringify(done)}\n\n`,
      ])
    );
    vi.stubGlobal("fetch", fetchMock);

    const events = await collect(streamChat(input));

    expect(events).toEqual([
      { event: "token", data: { delta: "voltagem é" } },
      { event: "done", data: done },
    ]);
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toMatch(/\/api\/v1\/chat\/stream$/);
    expect(JSON.parse(String(init.body))).toEqual({
      session_id: input.sessionId,
      client_request_id: input.clientRequestId,
      message: input.message,
      context_filters: { current_product_sku: "AF-400-220V" },
    });
  });

  it("treats EOF without done as an interrupted stream", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => sseResponse(['event: token\ndata: {"delta":"a"}\n\n'])));
    await expect(collect(streamChat(input))).rejects.toBeInstanceOf(StreamInterruptedError);
  });

  it("treats a network failure as an interrupted stream", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => Promise.reject(new TypeError("Failed to fetch"))));
    await expect(collect(streamChat(input))).rejects.toBeInstanceOf(StreamInterruptedError);
  });

  it("waits Retry-After on TURN_IN_PROGRESS and repeats the same request", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(errorResponse(409, "TURN_IN_PROGRESS", { "Retry-After": "0" }))
      .mockResolvedValueOnce(sseResponse([`event: done\ndata: ${JSON.stringify(done)}\n\n`]));
    vi.stubGlobal("fetch", fetchMock);

    await expect(collect(streamChat(input))).resolves.toHaveLength(1);
    const bodies = fetchMock.mock.calls.map(([, init]) => (init as RequestInit).body);
    expect(bodies[0]).toBe(bodies[1]);
  });

  it.each([
    [409, "IDEMPOTENCY_CONFLICT"],
    [410, "TURN_EXPIRED"],
    [422, "VALIDATION_ERROR"],
    [429, "RATE_LIMITED"],
  ])("does not retry HTTP %i %s", async (status, code) => {
    const fetchMock = vi.fn(async () => errorResponse(status, code));
    vi.stubGlobal("fetch", fetchMock);

    const failure = collect(streamChat(input));
    await expect(failure).rejects.toBeInstanceOf(ChatApiError);
    await expect(failure).rejects.toMatchObject({ status, code });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
