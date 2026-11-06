import { describe, it, expect } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import React from "react";
import SmartSalesPage from "@/app/page";

describe("UT-F01-01: SmartSalesPage e ContextualChatDrawer", () => {
  it("deve renderizar a vitrine de produtos e abrir o ContextualChatDrawer ao selecionar o item AF-400-220V", () => {
    render(<SmartSalesPage />);

    // 1. Verifica título da loja ou catálogo
    expect(screen.getByText(/SmartSales/i)).toBeInTheDocument();

    // 2. Localiza o produto base AF-400-220V
    const productCard = screen.getByTestId("product-card-AF-400-220V");
    expect(productCard).toBeInTheDocument();
    expect(screen.getByText(/Airfryer SmartChef 4L/i)).toBeInTheDocument();

    // 3. Inicialmente o drawer contextual do chat está fechado ou inativo
    const drawerBefore = screen.queryByTestId("contextual-chat-drawer");
    expect(drawerBefore).not.toBeInTheDocument();

    // 4. Usuário clica no card ou no botão de consulta contextual
    const consultButton = screen.getByTestId("consult-ai-btn-AF-400-220V");
    fireEvent.click(consultButton);

    // 5. O ContextualChatDrawer abre com o SKU ativo
    const drawerAfter = screen.getByTestId("contextual-chat-drawer");
    expect(drawerAfter).toBeInTheDocument();
    expect(drawerAfter).toHaveAttribute("data-sku", "AF-400-220V");

    // 6. Sugestões rápidas e input acessível estão presentes
    expect(screen.getByTestId("chat-prompt-input")).toBeInTheDocument();
    expect(screen.getByText(/Perguntas frequentes deste produto/i)).toBeInTheDocument();
  });

  it("deve fechar o drawer ao clicar no botão de fechar", () => {
    render(<SmartSalesPage />);

    // Abre o drawer
    const consultButton = screen.getByTestId("consult-ai-btn-AF-400-220V");
    fireEvent.click(consultButton);
    expect(screen.getByTestId("contextual-chat-drawer")).toBeInTheDocument();

    // Fecha o drawer
    const closeButton = screen.getByTestId("close-drawer-btn");
    fireEvent.click(closeButton);
    expect(screen.queryByTestId("contextual-chat-drawer")).not.toBeInTheDocument();
  });
});
