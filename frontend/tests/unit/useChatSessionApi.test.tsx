import { describe, expect, it, vi } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { StreamEvent } from "@/types/chat";
import { findProduct } from "@/lib/mock-data";

const api = vi.hoisted(() => {
  class StreamInterruptedError extends Error {}
  return {
    StreamInterruptedError,
    createSession: vi.fn(async () => "server-session"),
    deleteSession: vi.fn(async () => undefined),
    streamChat: vi.fn(),
  };
});

vi.mock("@/lib/chat-api", () => ({
  API_BASE_URL: "http://middleend.test",
  USE_REAL_API: true,
  ChatApiError: class ChatApiError extends Error {},
  ...api,
}));

import { useChatSession } from "@/hooks/use-chat-session";

const doneEvent: StreamEvent = {
  event: "done",
  data: { finish_reason: "stop", total_latency_ms: 5, tokens_used: 2 },
};

describe("useChatSession against the real middle-end", () => {
  it("reconnects once with the same client_request_id and discards the partial text", async () => {
    api.createSession.mockClear();
    api.streamChat.mockReset();
    api.streamChat
      .mockImplementationOnce(async function* () {
        yield { event: "token", data: { delta: "parcial " } };
        throw new api.StreamInterruptedError();
      })
      .mockImplementationOnce(async function* () {
        yield { event: "token", data: { delta: "Resposta completa." } };
        yield doneEvent;
      });
    const product = findProduct("AF-400-220V") ?? null;
    const { result } = renderHook(() => useChatSession());

    act(() => result.current.send("Qual a voltagem?", product));

    await waitFor(() => expect(result.current.isStreaming).toBe(false));
    const assistant = result.current.messages.at(-1);
    expect(assistant?.content).toBe("Resposta completa.");
    expect(assistant?.errorCode).toBeNull();
    expect(api.createSession).toHaveBeenCalledWith(null, expect.anything());
    const [first, second] = api.streamChat.mock.calls.map(([request]) => request);
    expect(first).toMatchObject({ sessionId: "server-session", currentProductSku: "AF-400-220V" });
    expect(second.clientRequestId).toBe(first.clientRequestId);
    expect(result.current.sessionId).toBe("server-session");
  });

  it("creates one session with null SKU, omits product SKU in catalog mode and reuses the session across products", async () => {
    api.createSession.mockClear();
    api.streamChat.mockReset();
    api.streamChat.mockImplementation(async function* () {
      yield { event: "token", data: { delta: "Ok." } };
      yield doneEvent;
    });
    const airfryer = findProduct("AF-400-220V")!;
    const coffee = findProduct("CF-15B-127V")!;
    const { result } = renderHook(() => useChatSession());

    act(() => result.current.send("Quero um PC", null));
    await waitFor(() => expect(result.current.isStreaming).toBe(false));

    act(() => result.current.send("E esta airfryer?", airfryer));
    await waitFor(() => expect(result.current.isStreaming).toBe(false));

    act(() => result.current.send("E esta cafeteira?", coffee));
    await waitFor(() => expect(result.current.isStreaming).toBe(false));

    expect(api.createSession).toHaveBeenCalledTimes(1);
    expect(api.createSession).toHaveBeenCalledWith(null, expect.anything());
    const requests = api.streamChat.mock.calls.map(([request]) => request);
    expect(requests).toEqual([
      expect.objectContaining({ sessionId: "server-session", currentProductSku: null }),
      expect.objectContaining({ sessionId: "server-session", currentProductSku: "AF-400-220V" }),
      expect.objectContaining({ sessionId: "server-session", currentProductSku: "CF-15B-127V" }),
    ]);
  });

  it("discards partial text, citations and cards when an error event arrives", async () => {
    api.streamChat.mockImplementationOnce(async function* () {
      yield { event: "token", data: { delta: "parcial" } };
      yield {
        event: "error",
        data: { code: "LLM_UNAVAILABLE", recoverable: true, fallback_message: "Tente de novo." },
      };
      yield { ...doneEvent, data: { ...doneEvent.data, finish_reason: "error" } };
    });
    const product = findProduct("AF-400-220V") ?? null;
    const { result } = renderHook(() => useChatSession());

    act(() => result.current.send("Pergunta", product));

    await waitFor(() => expect(result.current.isStreaming).toBe(false));
    const assistant = result.current.messages.at(-1);
    expect(assistant?.content).toBe("");
    expect(assistant?.errorFallback).toBe("Tente de novo.");
    expect(assistant?.citations).toEqual([]);
    expect(assistant?.recommendations).toEqual([]);
  });

  it("manual retry after a double interruption reuses the client_request_id (server state unknown)", async () => {
    api.streamChat.mockReset();
    const interrupted = async function* (): AsyncGenerator<StreamEvent> {
      yield { event: "token", data: { delta: "parcial" } };
      throw new api.StreamInterruptedError();
    };
    api.streamChat
      .mockImplementationOnce(interrupted)
      .mockImplementationOnce(interrupted)
      .mockImplementationOnce(async function* () {
        yield { event: "token", data: { delta: "Agora sim." } };
        yield doneEvent;
      });
    vi.spyOn(console, "warn").mockImplementation(() => undefined);
    const product = findProduct("AF-400-220V") ?? null;
    const { result } = renderHook(() => useChatSession());

    act(() => result.current.send("Pergunta", product));
    await waitFor(() => expect(result.current.messages.at(-1)?.errorCode).toBe("LLM_UNAVAILABLE"));
    await waitFor(() => expect(result.current.isStreaming).toBe(false));

    act(() => result.current.retry(result.current.messages.at(-1)!.id));
    await waitFor(() => expect(result.current.messages.at(-1)?.content).toBe("Agora sim."));

    const ids = api.streamChat.mock.calls.map(([request]) => request.clientRequestId);
    expect(ids).toHaveLength(3);
    expect(new Set(ids).size).toBe(1);
  });

  it("retries an interrupted turn with its own ID and SKU after another question on another page", async () => {
    api.streamChat.mockReset();
    const interrupted = async function* (): AsyncGenerator<StreamEvent> {
      yield { event: "token", data: { delta: "parcial" } };
      throw new api.StreamInterruptedError();
    };
    const answered = async function* (): AsyncGenerator<StreamEvent> {
      yield { event: "token", data: { delta: "Ok." } };
      yield doneEvent;
    };
    api.streamChat
      .mockImplementationOnce(interrupted)
      .mockImplementationOnce(interrupted)
      .mockImplementationOnce(answered)
      .mockImplementationOnce(answered);
    vi.spyOn(console, "warn").mockImplementation(() => undefined);
    const { result } = renderHook(() => useChatSession());

    act(() => result.current.send("Primeira", findProduct("AF-400-220V") ?? null));
    await waitFor(() => expect(result.current.messages.at(-1)?.errorCode).toBe("LLM_UNAVAILABLE"));
    await waitFor(() => expect(result.current.isStreaming).toBe(false));
    const interruptedId = result.current.messages[1].id;

    // The shopper navigates to another product page and asks there first.
    act(() => result.current.send("Segunda", findProduct("CF-15B-127V") ?? null));
    await waitFor(() => expect(result.current.messages.at(-1)?.content).toBe("Ok."));
    await waitFor(() => expect(result.current.isStreaming).toBe(false));

    act(() => result.current.retry(interruptedId));
    await waitFor(() => expect(api.streamChat).toHaveBeenCalledTimes(4));

    const requests = api.streamChat.mock.calls.map(([request]) => request);
    expect(requests[3].clientRequestId).toBe(requests[0].clientRequestId);
    expect(requests[2].clientRequestId).not.toBe(requests[0].clientRequestId);
    expect(requests[2].currentProductSku).toBe("CF-15B-127V");
    expect(requests[3].currentProductSku).toBe("AF-400-220V");
  });

  it("manual retry after a terminal error starts a new client_request_id", async () => {
    api.streamChat.mockReset();
    api.streamChat
      .mockImplementationOnce(async function* (): AsyncGenerator<StreamEvent> {
        yield* [];
        throw new Error("HTTP 500");
      })
      .mockImplementationOnce(async function* () {
        yield { event: "token", data: { delta: "Ok." } };
        yield doneEvent;
      });
    vi.spyOn(console, "warn").mockImplementation(() => undefined);
    const product = findProduct("AF-400-220V") ?? null;
    const { result } = renderHook(() => useChatSession());

    act(() => result.current.send("Pergunta", product));
    await waitFor(() => expect(result.current.messages.at(-1)?.errorCode).toBe("INTERNAL_ERROR"));
    await waitFor(() => expect(result.current.isStreaming).toBe(false));

    act(() => result.current.retry(result.current.messages.at(-1)!.id));
    await waitFor(() => expect(result.current.messages.at(-1)?.content).toBe("Ok."));

    const [first, second] = api.streamChat.mock.calls.map(([request]) => request.clientRequestId);
    expect(second).not.toBe(first);
  });
});
