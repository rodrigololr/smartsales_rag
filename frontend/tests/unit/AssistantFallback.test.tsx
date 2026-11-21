import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import type { ChatMessage, StreamErrorCode } from "@/types/chat";
import { AssistantMessage } from "@/components/chat/AssistantMessage";

const fallbackMessage = (code: StreamErrorCode): ChatMessage => ({
  id: "a1",
  role: "assistant",
  content: "",
  isStreaming: false,
  citations: [],
  recommendations: [],
  feedback: null,
  errorFallback: "Mensagem segura do gateway.",
  errorCode: code,
});

const renderFallback = (code: StreamErrorCode) => {
  const onRetry = vi.fn();
  render(
    <AssistantMessage
      message={fallbackMessage(code)}
      sessionId="s1"
      onRetry={onRetry}
      onFeedback={async () => undefined}
    />
  );
  return { onRetry, alert: screen.getByTestId("assistant-fallback-a1") };
};

describe("Alerta de fallback por código", () => {
  it.each([
    ["LOW_SIMILARITY_FALLBACK", "Informação não encontrada no manual", "info"],
    ["GUARDRAIL_BLOCKED", "Pergunta fora do escopo do consultor", "warning"],
  ] as const)("%s é uma resposta segura esperada (\"%s\"), sem retry", (code, title, tone) => {
    const { alert } = renderFallback(code);
    expect(alert).toHaveTextContent(title);
    expect(alert).toHaveTextContent("Mensagem segura do gateway.");
    expect(alert).toHaveAttribute("data-tone", tone);
    expect(alert).not.toHaveTextContent(code);
    expect(screen.queryByRole("button", { name: /Tentar novamente/ })).not.toBeInTheDocument();
  });

  it.each([
    ["LLM_UNAVAILABLE", "Consultor indisponível no momento"],
    ["INTERNAL_ERROR", "Não foi possível concluir a resposta"],
  ] as const)("%s é falha: tom de erro com Tentar novamente na coluna do texto", (code, title) => {
    const { alert, onRetry } = renderFallback(code);
    expect(alert).toHaveTextContent(title);
    expect(alert).toHaveAttribute("data-tone", "error");
    expect(alert).not.toHaveTextContent(code);

    const retry = screen.getByRole("button", { name: /Tentar novamente/ });
    // A third grid child would open a new row under the icon and squeeze the text at 390px.
    expect(retry.parentElement).toHaveClass("col-start-2");
    fireEvent.click(retry);
    expect(onRetry).toHaveBeenCalledWith("a1");
  });
});
