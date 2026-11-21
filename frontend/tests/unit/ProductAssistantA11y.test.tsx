import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import type { ChatMessage } from "@/types/chat";
import type { ChatSession } from "@/hooks/use-chat-session";
import { ProductAssistant } from "@/components/chat/ProductAssistant";
import { findProduct } from "@/lib/mock-data";

const product = findProduct("AF-400-220V")!;

const message = (overrides: Partial<ChatMessage>): ChatMessage => ({
  id: "m",
  role: "assistant",
  content: "",
  isStreaming: false,
  citations: [],
  recommendations: [],
  feedback: null,
  errorFallback: null,
  errorCode: null,
  ...overrides,
});

const question = message({ id: "u1", role: "user", content: "Qual a voltagem?" });

const chatWith = (overrides: Partial<ChatSession>): ChatSession => ({
  sessionId: "s1",
  messages: [],
  isStreaming: false,
  send: vi.fn(),
  retry: vi.fn(),
  reset: vi.fn(),
  submitFeedback: vi.fn(async () => undefined),
  ...overrides,
});

describe("Consultor acessível durante o streaming", () => {
  it("não anuncia tokens: aria-busy no histórico e só a resposta final na região viva", () => {
    const streaming = chatWith({
      isStreaming: true,
      messages: [question, message({ id: "a1", content: "Opera em", isStreaming: true })],
    });
    const { rerender } = render(<ProductAssistant product={product} chat={streaming} />);

    const log = screen.getByTestId("chat-log");
    expect(log).not.toHaveAttribute("aria-live");
    expect(log).toHaveAttribute("aria-busy", "true");
    const announcer = screen.getByTestId("chat-announcer");
    expect(announcer).toHaveAttribute("aria-live", "polite");
    expect(announcer).toBeEmptyDOMElement();

    rerender(
      <ProductAssistant
        product={product}
        chat={chatWith({ messages: [question, message({ id: "a1", content: "Opera em 220V." })] })}
      />
    );
    expect(log).toHaveAttribute("aria-busy", "false");
    expect(announcer).toHaveTextContent("Opera em 220V.");
  });

  it("anuncia o fallback com o título amigável, sem o código", () => {
    render(
      <ProductAssistant
        product={product}
        chat={chatWith({
          messages: [
            question,
            message({ id: "a1", errorFallback: "Não consta no manual.", errorCode: "LOW_SIMILARITY_FALLBACK" }),
          ],
        })}
      />
    );
    const announcer = screen.getByTestId("chat-announcer");
    expect(announcer).toHaveTextContent("Informação não encontrada no manual. Não consta no manual.");
    expect(announcer).not.toHaveTextContent("LOW_SIMILARITY_FALLBACK");
  });

  it("mantém o campo habilitado (e o foco) enquanto responde; só o envio fica bloqueado", () => {
    const chat = chatWith({
      isStreaming: true,
      messages: [question, message({ id: "a1", isStreaming: true })],
    });
    render(<ProductAssistant product={product} chat={chat} />);

    const input = screen.getByTestId("chat-prompt-input");
    expect(input).toBeEnabled();
    input.focus();
    fireEvent.change(input, { target: { value: "E a potência?" } });
    fireEvent.submit(input.closest("form")!);

    expect(chat.send).not.toHaveBeenCalled();
    expect(screen.getByLabelText("Enviar pergunta")).toBeDisabled();
    expect(input).toHaveValue("E a potência?");
    expect(input).toHaveFocus();
  });
});
