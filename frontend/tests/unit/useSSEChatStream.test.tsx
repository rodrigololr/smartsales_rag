import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useSSEChatStream } from "@/hooks/useSSEChatStream";

function createMockStream(chunks: string[], status = 200) {
  const stream = new ReadableStream({
    start(controller) {
      for (const chunk of chunks) {
        controller.enqueue(new TextEncoder().encode(chunk));
      }
      controller.close();
    },
  });
  return new Response(stream, {
    status,
    headers: { "Content-Type": "text/event-stream" },
  });
}

describe("useSSEChatStream Hook (F02 TDD)", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("UT-F02-01: deve processar tokens progressivamente, controlar isStreaming e finalizar em done", async () => {
    const sseChunks = [
      'event: metadata\ndata: {"message_id": "msg-1", "ttft_ms": 120, "cache_hit": false}\n\n',
      'event: token\ndata: {"delta": "A "}\n\n',
      'event: token\ndata: {"delta": "Airfryer "}\n\n',
      'event: token\ndata: {"delta": "possui "}\n\n',
      'event: token\ndata: {"delta": "4 Litros."}\n\n',
      'event: done\ndata: {"finish_reason": "stop", "total_latency_ms": 450, "tokens_used": 15}\n\n',
    ];

    vi.spyOn(global, "fetch").mockResolvedValueOnce(createMockStream(sseChunks));

    const { result } = renderHook(() => useSSEChatStream("test-session"));

    expect(result.current.isStreaming).toBe(false);
    expect(result.current.connectionState).toBe("IDLE");

    let sendPromise: Promise<void>;
    act(() => {
      sendPromise = result.current.sendMessage("Qual a capacidade?", {
        skuContext: "AF-400-220V",
        voltagePreference: "220V",
      });
    });

    // Logo após o envio, deve entrar em streaming ativo
    expect(result.current.isStreaming).toBe(true);
    expect(result.current.connectionState).toBe("CONNECTING");

    await act(async () => {
      await sendPromise;
    });

    // Após processar todo o stream e o done
    expect(result.current.isStreaming).toBe(false);
    expect(result.current.connectionState).toBe("COMPLETED");

    // Verifica mensagens acumuladas
    const msgs = result.current.messages;
    expect(msgs).toHaveLength(2);
    expect(msgs[0].role).toBe("user");
    expect(msgs[0].content).toBe("Qual a capacidade?");

    expect(msgs[1].role).toBe("assistant");
    expect(msgs[1].content).toBe("A Airfryer possui 4 Litros.");
    expect(msgs[1].isStreaming).toBe(false);
    expect(msgs[1].ttftMs).toBe(120);
  });

  it("UT-F02-02: deve substituir atômica e seguramente o texto em caso de evento correction (STREAM_INTERRUPTED)", async () => {
    const sseChunks = [
      'event: metadata\ndata: {"message_id": "msg-2", "ttft_ms": 150}\n\n',
      'event: token\ndata: {"delta": "Este modelo "}\n\n',
      'event: token\ndata: {"delta": "127V "}\n\n',
      'event: token\ndata: {"delta": "opera em..."}\n\n',
      'event: correction\ndata: {"violation_code": "STREAM_INTERRUPTED", "content": "Este modelo opera exclusivamente em 220V conforme o manual oficial."}\n\n',
      'event: done\ndata: {"finish_reason": "stop", "total_latency_ms": 500}\n\n',
    ];

    vi.spyOn(global, "fetch").mockResolvedValueOnce(createMockStream(sseChunks));

    const { result } = renderHook(() => useSSEChatStream("test-session"));

    await act(async () => {
      await result.current.sendMessage("Funciona em 127V?");
    });

    const assistantMsg = result.current.messages[1];
    expect(assistantMsg.content).toBe(
      "Este modelo opera exclusivamente em 220V conforme o manual oficial."
    );
    expect(assistantMsg.wasCorrected).toBe(true);
  });

  it("deve descartar conteúdo parcial e exibir fallback_message em caso de evento error", async () => {
    const sseChunks = [
      'event: metadata\ndata: {"message_id": "msg-3"}\n\n',
      'event: token\ndata: {"delta": "Texto parcial que deve ser descartado..."}\n\n',
      'event: error\ndata: {"code": "LOW_SIMILARITY_FALLBACK", "recoverable": true, "fallback_message": "Informação não encontrada no manual."}\n\n',
      'event: done\ndata: {"finish_reason": "fallback"}\n\n',
    ];

    vi.spyOn(global, "fetch").mockResolvedValueOnce(createMockStream(sseChunks));

    const { result } = renderHook(() => useSSEChatStream());

    await act(async () => {
      await result.current.sendMessage("Receita de bolo?");
    });

    const assistantMsg = result.current.messages[1];
    expect(assistantMsg.content).toBe("");
    expect(assistantMsg.errorFallback).toBe("Informação não encontrada no manual.");
    expect(assistantMsg.errorCode).toBe("LOW_SIMILARITY_FALLBACK");
    expect(result.current.connectionState).toBe("COMPLETED");
  });

  it("deve reiniciar a sessão e limpar mensagens ao chamar resetSession", async () => {
    const fetchMock = vi.spyOn(global, "fetch").mockResolvedValueOnce(
      new Response(null, { status: 204 })
    );

    const { result } = renderHook(() => useSSEChatStream("session-to-reset"));

    await act(async () => {
      await result.current.resetSession();
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/sessions/session-to-reset",
      expect.objectContaining({ method: "DELETE" })
    );
    expect(result.current.sessionId).not.toBe("session-to-reset");
    expect(result.current.messages).toEqual([]);
    expect(result.current.connectionState).toBe("IDLE");
  });
});
