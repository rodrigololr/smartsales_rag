"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { Product } from "@/types/catalog";
import type {
  ChatMessage,
  FeedbackRating,
  FeedbackReasonCategory,
  StreamEvent,
} from "@/types/chat";
import { createId } from "@/lib/format";
import { mockFeedback, streamMockChat } from "@/lib/mock-api";
import {
  API_BASE_URL,
  StreamInterruptedError,
  createSession,
  deleteSession,
  streamChat,
} from "@/lib/chat-api";

const USE_REAL_API = API_BASE_URL !== "";
const MAX_AUTOMATIC_RECONNECTS = 1;
const FAILURE_MESSAGE =
  "Não foi possível concluir a consulta agora. Tente novamente em instantes.";

const emptyAssistantMessage = (id: string): ChatMessage => ({
  id,
  role: "assistant",
  content: "",
  isStreaming: true,
  citations: [],
  recommendations: [],
  feedback: null,
  errorFallback: null,
  errorCode: null,
});

const isAbort = (error: unknown): boolean =>
  error instanceof Error && error.name === "AbortError";

export function useChatSession(product: Product | null) {
  const [sessionId, setSessionId] = useState<string>(() => createId());
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const controllerRef = useRef<AbortController | null>(null);
  // Server session (real API only); created lazily on the first question.
  const serverSessionRef = useRef<string | null>(null);

  const reset = useCallback(() => {
    controllerRef.current?.abort();
    controllerRef.current = null;
    const serverSession = serverSessionRef.current;
    serverSessionRef.current = null;
    if (serverSession) {
      deleteSession(serverSession).catch((error: unknown) =>
        console.warn("chat_session_delete_failed", error)
      );
    }
    setMessages([]);
    setIsStreaming(false);
    setSessionId(createId());
  }, []);

  useEffect(() => {
    return () => {
      controllerRef.current?.abort();
    };
  }, []);

  const patchAssistant = useCallback(
    (id: string, patch: Partial<ChatMessage>) => {
      setMessages((previous) =>
        previous.map((message) =>
          message.id === id ? { ...message, ...patch } : message
        )
      );
    },
    []
  );

  const applyEvent = useCallback(
    (assistantId: string, event: StreamEvent) => {
      switch (event.event) {
        case "metadata":
          patchAssistant(assistantId, {
            ttftMs: event.data.ttft_ms,
            cacheHit: event.data.cache_hit,
          });
          break;
        case "token":
          setMessages((previous) =>
            previous.map((message) =>
              message.id === assistantId
                ? { ...message, content: message.content + event.data.delta }
                : message
            )
          );
          break;
        case "correction":
          patchAssistant(assistantId, { content: event.data.content, wasCorrected: true });
          break;
        case "citations":
          patchAssistant(assistantId, { citations: event.data.citations });
          break;
        case "recommendations":
          patchAssistant(assistantId, { recommendations: event.data.products });
          break;
        case "error":
          // Contract: discard every partial text/citation/card; later cards are new ones.
          patchAssistant(assistantId, {
            content: "",
            citations: [],
            recommendations: [],
            wasCorrected: false,
            errorFallback: event.data.fallback_message,
            errorCode: event.data.code,
          });
          break;
        case "done":
          patchAssistant(assistantId, { isStreaming: false });
          break;
      }
    },
    [patchAssistant]
  );

  const openStream = useCallback(
    async function* (
      activeProduct: Product,
      prompt: string,
      clientRequestId: string,
      signal: AbortSignal
    ): AsyncGenerator<StreamEvent> {
      if (!USE_REAL_API) {
        yield* streamMockChat({ sessionId, message: prompt, product: activeProduct }, signal);
        return;
      }
      if (!serverSessionRef.current) {
        serverSessionRef.current = await createSession(activeProduct.sku, signal);
        setSessionId(serverSessionRef.current);
      }
      yield* streamChat(
        {
          sessionId: serverSessionRef.current,
          clientRequestId,
          message: prompt,
          currentProductSku: activeProduct.sku,
        },
        signal
      );
    },
    [sessionId]
  );

  const run = useCallback(
    async (prompt: string, replaceAssistantId?: string) => {
      if (!product || !prompt.trim() || controllerRef.current) return;
      const question = prompt.trim();

      const assistantId = replaceAssistantId ?? createId();
      const userMessage: ChatMessage = {
        id: createId(),
        role: "user",
        content: question,
        isStreaming: false,
        citations: [],
        recommendations: [],
        feedback: null,
        errorFallback: null,
        errorCode: null,
      };

      setMessages((previous) => {
        const base = replaceAssistantId
          ? previous.filter((message) => message.id !== replaceAssistantId)
          : [...previous, userMessage];
        return [...base, emptyAssistantMessage(assistantId)];
      });
      setIsStreaming(true);

      const controller = new AbortController();
      controllerRef.current = controller;
      // One ID per explicit question, kept on the automatic reconnect.
      const clientRequestId = createId();

      try {
        for (let reconnects = 0; ; reconnects++) {
          try {
            for await (const event of openStream(product, question, clientRequestId, controller.signal)) {
              applyEvent(assistantId, event);
            }
            break;
          } catch (error) {
            if (!(error instanceof StreamInterruptedError) || reconnects >= MAX_AUTOMATIC_RECONNECTS) {
              throw error;
            }
            patchAssistant(assistantId, emptyAssistantMessage(assistantId));
          }
        }
      } catch (error) {
        if (isAbort(error)) return;
        console.warn("chat_stream_failed", error);
        patchAssistant(assistantId, {
          content: "",
          citations: [],
          recommendations: [],
          isStreaming: false,
          errorCode: error instanceof StreamInterruptedError ? "LLM_UNAVAILABLE" : "INTERNAL_ERROR",
          errorFallback: FAILURE_MESSAGE,
        });
      } finally {
        // A reset may already have started another turn; only clear our own.
        if (controllerRef.current === controller) {
          controllerRef.current = null;
          setIsStreaming(false);
          patchAssistant(assistantId, { isStreaming: false });
        }
      }
    },
    [applyEvent, openStream, patchAssistant, product]
  );

  const send = useCallback(
    (prompt: string) => {
      void run(prompt);
    },
    [run]
  );

  const retry = useCallback(
    (assistantId: string) => {
      const index = messages.findIndex((message) => message.id === assistantId);
      if (index < 0) return;
      const userMessage = [...messages.slice(0, index)]
        .reverse()
        .find((message) => message.role === "user");
      if (!userMessage) return;
      void run(userMessage.content, assistantId);
    },
    [messages, run]
  );

  const submitFeedback = useCallback(
    async (
      messageId: string,
      rating: FeedbackRating,
      reason?: FeedbackReasonCategory
    ) => {
      await mockFeedback({
        session_id: sessionId,
        message_id: messageId,
        rating,
        reason_category: rating === "DISLIKE" ? reason : undefined,
      });
      patchAssistant(messageId, {
        feedback: rating,
        feedbackReason: reason ?? null,
      });
    },
    [patchAssistant, sessionId]
  );

  return {
    sessionId,
    messages,
    isStreaming,
    send,
    retry,
    reset,
    submitFeedback,
  };
}

export type ChatSession = ReturnType<typeof useChatSession>;
