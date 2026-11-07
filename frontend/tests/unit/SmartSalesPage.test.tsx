import { describe, expect, it } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import SmartSalesPage from "@/app/page";

describe("UT-F01-01: catálogo comum com imagens", () => {
  it("mostra os produtos com foto, preço e link para a página do item", () => {
    render(<SmartSalesPage />);

    expect(within(screen.getByRole("banner")).getByText(/SmartSales/i)).toBeInTheDocument();
    const card = screen.getByTestId("product-card-AF-400-220V");
    expect(card).toHaveAttribute("href", "/produto/AF-400-220V");
    expect(within(card).getByRole("img", { name: "Airfryer SmartChef 4L" })).toHaveAttribute(
      "src",
      "/images/airfryer-4l.svg"
    );
    expect(within(card).getByText("R$ 499,90")).toBeInTheDocument();
    expect(screen.queryByTestId("product-assistant")).not.toBeInTheDocument();
  });

  it("filtra por voltagem e busca", () => {
    render(<SmartSalesPage />);

    fireEvent.click(screen.getByRole("button", { name: "127V" }));
    expect(screen.getByTestId("product-card-CF-15B-127V")).toBeInTheDocument();
    expect(screen.queryByTestId("product-card-AF-400-220V")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Todas" }));
    fireEvent.change(screen.getByLabelText("Buscar produtos no catálogo"), {
      target: { value: "família" },
    });
    expect(screen.getByText("Nenhum produto encontrado")).toBeInTheDocument();
  });
});
