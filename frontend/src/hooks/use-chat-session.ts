"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { Product } from "@/types/catalog";
import type {
  ChatMessage,
  FeedbackRating,
  FeedbackReasonCategory,
} from "@/types/chat";
import { createId } from "@/lib/format";
import { mockFeedback, streamMockChat } from "@/lib/mock-api";

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

export function useChatSession(product: Product | null) {
  const [sessionId, setSessionId] = useState<string>(() => createId());
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const controllerRef = useRef<AbortController | null>(null);

  const reset = useCallback(() => {
    controllerRef.current?.abort();
    controllerRef.current = null;
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

  const run = useCallback(
    async (prompt: string, replaceAssistantId?: string) => {
      if (!product || !prompt.trim() || isStreaming) return;

      const assistantId = replaceAssistantId ?? createId();
      const userMessage: ChatMessage = {
        id: createId(),
        role: "user",
        content: prompt.trim(),
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

      try {
        for await (const event of streamMockChat(
          { sessionId, message: prompt.trim(), product },
          controller.signal
        )) {
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
              patchAssistant(assistantId, {
                content: event.data.content,
                wasCorrected: true,
              });
              break;
            case "citations":
              patchAssistant(assistantId, { citations: event.data.citations });
              break;
            case "recommendations":
              patchAssistant(assistantId, {
                recommendations: event.data.products,
              });
              break;
            case "error":
              patchAssistant(assistantId, {
                content: "",
                errorFallback: event.data.fallback_message,
                errorCode: event.data.code,
                isStreaming: false,
              });
              break;
            case "done":
              patchAssistant(assistantId, { isStreaming: false });
              break;
          }
        }
      } catch (error) {
        if (error instanceof Error && error.name === "AbortError") return;
        patchAssistant(assistantId, {
          content: "",
          isStreaming: false,
          errorCode: "LLM_UNAVAILABLE",
          errorFallback:
            "Não foi possível concluir a consulta agora. Tente novamente em instantes.",
        });
      } finally {
        controllerRef.current = null;
        setIsStreaming(false);
        patchAssistant(assistantId, { isStreaming: false });
      }
    },
    [isStreaming, patchAssistant, product, sessionId]
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
