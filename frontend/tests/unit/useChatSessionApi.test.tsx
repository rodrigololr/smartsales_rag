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
    const { result } = renderHook(() => useChatSession(product));

    act(() => result.current.send("Qual a voltagem?"));

    await waitFor(() => expect(result.current.isStreaming).toBe(false));
    const assistant = result.current.messages.at(-1);
    expect(assistant?.content).toBe("Resposta completa.");
    expect(assistant?.errorCode).toBeNull();
    expect(api.createSession).toHaveBeenCalledWith("AF-400-220V", expect.anything());
    const [first, second] = api.streamChat.mock.calls.map(([request]) => request);
    expect(first).toMatchObject({ sessionId: "server-session", currentProductSku: "AF-400-220V" });
    expect(second.clientRequestId).toBe(first.clientRequestId);
    expect(result.current.sessionId).toBe("server-session");
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
    const { result } = renderHook(() => useChatSession(product));

    act(() => result.current.send("Pergunta"));

    await waitFor(() => expect(result.current.isStreaming).toBe(false));
    const assistant = result.current.messages.at(-1);
    expect(assistant?.content).toBe("");
    expect(assistant?.errorFallback).toBe("Tente de novo.");
    expect(assistant?.citations).toEqual([]);
    expect(assistant?.recommendations).toEqual([]);
  });
});
