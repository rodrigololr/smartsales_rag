"use client";

import { useState, useCallback, useRef } from "react";
import {
  ChatMessage,
  ManualCitation,
  ProductCardData,
  StreamErrorCode,
} from "@/types/chat";
import { SSEBufferParser } from "@/utils/sseParser";

export type VisualConnectionState =
  | "IDLE"
  | "CONNECTING"
  | "STREAMING"
  | "ENRICHING"
  | "ERROR"
  | "COMPLETED";

export interface SendMessageOptions {
  skuContext?: string;
  voltagePreference?: string;
  apiEndpoint?: string;
}

export function generateUUID(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

export function useSSEChatStream(initialSessionId?: string) {
  const [sessionId, setSessionId] = useState<string>(
    () => initialSessionId || generateUUID()
  );
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [connectionState, setConnectionState] =
    useState<VisualConnectionState>("IDLE");
  const [isStreaming, setIsStreaming] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Armazena payload do último envio para retries resilientes (R07)
  const lastRequestRef = useRef<{
    prompt: string;
    clientRequestId: string;
    options?: SendMessageOptions;
    hasRetried: boolean;
  } | null>(null);

  const abortControllerRef = useRef<AbortController | null>(null);

  const executeStream = useCallback(
    async (
      prompt: string,
      clientRequestId: string,
      assistantMessageId: string,
      options?: SendMessageOptions
    ) => {
      const endpoint = options?.apiEndpoint || "/api/v1/chat/stream";
      abortControllerRef.current = new AbortController();

      const payload = {
        session_id: sessionId,
        message: prompt,
        client_request_id: clientRequestId,
        sku_context: options?.skuContext,
        voltage_preference: options?.voltagePreference,
      };

      let doneReceived = false;
      const parser = new SSEBufferParser();

      try {
        const response = await fetch(endpoint, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Accept: "text/event-stream",
          },
          body: JSON.stringify(payload),
          signal: abortControllerRef.current.signal,
        });

        if (!response.ok) {
          if (response.status === 409) {
            throw new Error("TURN_IN_PROGRESS");
          }
          throw new Error(`HTTP_${response.status}`);
        }

        if (!response.body) {
          throw new Error("EMPTY_RESPONSE_BODY");
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          const chunkText = decoder.decode(value, { stream: true });
          const events = parser.feed(chunkText);

          for (const ev of events) {
            switch (ev.event) {
              case "metadata": {
                setMessages((prev) =>
                  prev.map((msg) =>
                    msg.id === assistantMessageId
                      ? {
                          ...msg,
                          ttftMs: ev.data.ttft_ms,
                          cacheHit: ev.data.cache_hit,
                        }
                      : msg
                  )
                );
                break;
              }

              case "token": {
                setConnectionState("STREAMING");
                const delta = ev.data.delta || "";
                setMessages((prev) =>
                  prev.map((msg) =>
                    msg.id === assistantMessageId
                      ? { ...msg, content: msg.content + delta }
                      : msg
                  )
                );
                break;
              }

              case "correction": {
                // Substituição atômica pelo texto seguro validado (UT-F02-02)
                setMessages((prev) =>
                  prev.map((msg) =>
                    msg.id === assistantMessageId
                      ? {
                          ...msg,
                          content: ev.data.content,
                          wasCorrected: true,
                        }
                      : msg
                  )
                );
                break;
              }

              case "citations": {
                setConnectionState("ENRICHING");
                const newCitations: ManualCitation[] = ev.data.citations || [];
                setMessages((prev) =>
                  prev.map((msg) =>
                    msg.id === assistantMessageId
                      ? { ...msg, citations: newCitations }
                      : msg
                  )
                );
                break;
              }

              case "recommendations": {
                setConnectionState("ENRICHING");
                const newRecs: ProductCardData[] = ev.data.products || [];
                setMessages((prev) =>
                  prev.map((msg) =>
                    msg.id === assistantMessageId
                      ? { ...msg, recommendations: newRecs }
                      : msg
                  )
                );
                break;
              }

              case "error": {
                // Descarta conteúdo parcial em caso de erro/fallback e exibe mensagem segura
                setConnectionState("ERROR");
                setMessages((prev) =>
                  prev.map((msg) =>
                    msg.id === assistantMessageId
                      ? {
                          ...msg,
                          content: "",
                          errorFallback: ev.data.fallback_message,
                          errorCode: ev.data.code as StreamErrorCode,
                        }
                      : msg
                  )
                );
                break;
              }

              case "done": {
                doneReceived = true;
                setConnectionState("COMPLETED");
                setIsStreaming(false);
                setMessages((prev) =>
                  prev.map((msg) =>
                    msg.id === assistantMessageId
                      ? { ...msg, isStreaming: false }
                      : msg
                  )
                );
                break;
              }
            }
          }
        }
      } catch (err: any) {
        // Se a conexão cair antes de done, tenta reconectar uma única vez com o mesmo client_request_id
        if (!doneReceived && lastRequestRef.current && !lastRequestRef.current.hasRetried) {
          lastRequestRef.current.hasRetried = true;
          // Descarta texto parcial e retenta
          setMessages((prev) =>
            prev.map((msg) =>
              msg.id === assistantMessageId ? { ...msg, content: "" } : msg
            )
          );
          return executeStream(prompt, clientRequestId, assistantMessageId, options);
        }

        setConnectionState("ERROR");
        setIsStreaming(false);
        setErrorMessage(err.message || "Erro de conexão com o assistente.");
        setMessages((prev) =>
          prev.map((msg) =>
            msg.id === assistantMessageId
              ? {
                  ...msg,
                  isStreaming: false,
                  errorFallback:
                    msg.errorFallback ||
                    "Não foi possível concluir a resposta. Por favor, tente novamente.",
                }
              : msg
          )
        );
      } finally {
        if (!isStreaming) {
          setIsStreaming(false);
        }
      }
    },
    [sessionId, isStreaming]
  );

  const sendMessage = useCallback(
    async (prompt: string, options?: SendMessageOptions) => {
      if (!prompt.trim() || isStreaming) return;

      const userMessageId = generateUUID();
      const assistantMessageId = generateUUID();
      const clientRequestId = generateUUID();

      const userMessage: ChatMessage = {
        id: userMessageId,
        role: "user",
        content: prompt,
        isStreaming: false,
        citations: [],
        recommendations: [],
      };

      const assistantMessage: ChatMessage = {
        id: assistantMessageId,
        role: "assistant",
        content: "",
        isStreaming: true,
        citations: [],
        recommendations: [],
      };

      setMessages((prev) => [...prev, userMessage, assistantMessage]);
      setIsStreaming(true);
      setConnectionState("CONNECTING");
      setErrorMessage(null);

      lastRequestRef.current = {
        prompt,
        clientRequestId,
        options,
        hasRetried: false,
      };

      await executeStream(prompt, clientRequestId, assistantMessageId, options);
    },
    [isStreaming, executeStream]
  );

  const retryLastMessage = useCallback(() => {
    if (!lastRequestRef.current) return;
    const { prompt, clientRequestId, options } = lastRequestRef.current;
    lastRequestRef.current.hasRetried = false;

    const assistantMessageId = generateUUID();
    const assistantMessage: ChatMessage = {
      id: assistantMessageId,
      role: "assistant",
      content: "",
      isStreaming: true,
      citations: [],
      recommendations: [],
    };

    setMessages((prev) => [...prev, assistantMessage]);
    setIsStreaming(true);
    setConnectionState("CONNECTING");
    executeStream(prompt, clientRequestId, assistantMessageId, options);
  }, [executeStream]);

  const resetSession = useCallback(async () => {
    try {
      await fetch(`/api/v1/sessions/${sessionId}`, { method: "DELETE" });
    } catch {
      // Ignora falha de rede ao deletar sessão remota
    }
    const newSession = generateUUID();
    setSessionId(newSession);
    setMessages([]);
    setConnectionState("IDLE");
    setIsStreaming(false);
    setErrorMessage(null);
    lastRequestRef.current = null;
  }, [sessionId]);

  return {
    sessionId,
    messages,
    connectionState,
    isStreaming,
    errorMessage,
    sendMessage,
    retryLastMessage,
    resetSession,
  };
}
