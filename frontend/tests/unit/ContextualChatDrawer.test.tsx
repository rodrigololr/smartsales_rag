import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, act } from "@testing-library/react";
import React from "react";
import { ContextualChatDrawer } from "@/components/chat/ContextualChatDrawer";
import { Product } from "@/types/catalog";

const MOCK_PRODUCT: Product = {
  sku: "AF-400-220V",
  name: "Airfryer SmartChef 4L",
  brand: "SmartChef",
  category: "Eletroportáteis",
  subcategory: "Fritadeiras Elétricas",
  price: 499.90,
  stock_quantity: 15,
  voltage: "220V",
  capacity_liters: 4.0,
  power_watts: 1500,
  image_url: "/images/airfryer-4l.jpg",
  description: "Fritadeira sem óleo com controle digital de temperatura.",
};

describe("ContextualChatDrawer Component (F02 Integration)", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("não deve renderizar quando isOpen é false ou product é null", () => {
    const { rerender } = render(
      <ContextualChatDrawer product={MOCK_PRODUCT} isOpen={false} onClose={vi.fn()} />
    );
    expect(screen.queryByTestId("contextual-chat-drawer")).not.toBeInTheDocument();

    rerender(<ContextualChatDrawer product={null} isOpen={true} onClose={vi.fn()} />);
    expect(screen.queryByTestId("contextual-chat-drawer")).not.toBeInTheDocument();
  });

  it("deve renderizar o contexto do produto e disparar envio ao submeter o formulário", async () => {
    const mockStream = new ReadableStream({
      start(controller) {
        controller.enqueue(
          new TextEncoder().encode(
            'event: metadata\ndata: {"message_id": "msg-1"}\n\nevent: token\ndata: {"delta": "Sim, é 220V."}\n\nevent: done\ndata: {"finish_reason": "stop"}\n\n'
          )
        );
        controller.close();
      },
    });

    vi.spyOn(global, "fetch").mockResolvedValueOnce(
      new Response(mockStream, {
        status: 200,
        headers: { "Content-Type": "text/event-stream" },
      })
    );

    render(
      <ContextualChatDrawer product={MOCK_PRODUCT} isOpen={true} onClose={vi.fn()} />
    );

    expect(screen.getByTestId("contextual-chat-drawer")).toBeInTheDocument();
    expect(screen.getByText(/AF-400-220V/i)).toBeInTheDocument();

    const input = screen.getByTestId("chat-prompt-input");
    fireEvent.change(input, { target: { value: "Qual é a voltagem?" } });

    const sendBtn = screen.getByTestId("send-prompt-btn");
    await act(async () => {
      fireEvent.click(sendBtn);
    });

    // Deve exibir mensagem do usuário e resposta do assistente
    expect(screen.getByText("Qual é a voltagem?")).toBeInTheDocument();
    expect(await screen.findByText("Sim, é 220V.")).toBeInTheDocument();
  });

  it("deve chamar onClose ao clicar no botão de fechar", () => {
    const handleClose = vi.fn();
    render(
      <ContextualChatDrawer product={MOCK_PRODUCT} isOpen={true} onClose={handleClose} />
    );

    fireEvent.click(screen.getByTestId("close-drawer-btn"));
    expect(handleClose).toHaveBeenCalledTimes(1);
  });
});
