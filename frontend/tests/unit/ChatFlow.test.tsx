import { describe, expect, it } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import SmartSalesPage from "@/app/page";

describe("UT-F02-01: streaming mockado do Consultor IA", () => {
  it("envia uma sugestão e exibe resposta, citação, cards e feedback", async () => {
    render(<SmartSalesPage />);

    fireEvent.click(screen.getByTestId("consult-ai-btn-AF-400-220V"));
    fireEvent.click(screen.getByTestId("quick-suggestion-0"));

    expect(
      await screen.findByText(/A Airfryer SmartChef 4L opera exclusivamente em 220V/, undefined, {
        timeout: 4000,
      })
    ).toBeInTheDocument();

    expect(await screen.findByTestId("citation-list")).toBeInTheDocument();
    expect(screen.getByText(/Manual Airfryer SmartChef 4L — p\. 6/)).toBeInTheDocument();
    expect(await screen.findByTestId("recommendation-carousel")).toBeInTheDocument();
    expect(screen.getByTestId("recommendation-card-AF-400-220V")).toBeInTheDocument();
    expect(
      await screen.findByTestId(/^feedback-like-/, undefined, { timeout: 4000 })
    ).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("reset-chat-btn"));
    expect(
      screen.getByText(/Perguntas frequentes deste produto/i)
    ).toBeInTheDocument();
  });

  it("exibe fallback seguro quando a pergunta está fora dos manuais", async () => {
    render(<SmartSalesPage />);

    fireEvent.click(screen.getByTestId("consult-ai-btn-AF-400-220V"));
    fireEvent.change(screen.getByTestId("chat-prompt-input"), {
      target: { value: "Qual é a garantia vitalícia e o prazo de entrega?" },
    });
    fireEvent.click(screen.getByLabelText("Enviar pergunta"));

    const fallback = await screen.findByTestId(/^assistant-fallback-/, undefined, {
      timeout: 4000,
    });
    expect(fallback).toHaveTextContent(/Não encontrei essa informação/i);
    expect(fallback).toHaveTextContent(/LOW_SIMILARITY_FALLBACK/);
    expect(screen.getByText(/Tentar novamente/i)).toBeInTheDocument();
    expect(screen.queryByTestId("citation-list")).not.toBeInTheDocument();
  });
});
