import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { ProductDetailPanel } from "@/components/shop/ProductDetailPanel";
import { findProduct } from "@/lib/mock-data";

const mockCheckout = vi.hoisted(() => vi.fn(() => new Promise<never>(() => {})));
vi.mock("@/lib/mock-api", () => ({ mockCheckout }));

describe("ProductDetailPanel checkout", () => {
  it("registra um único checkout mesmo quando o painel re-renderiza", () => {
    const product = findProduct("AF-400-220V");
    if (!product) throw new Error("Produto base ausente no mock");
    const noop = () => {};

    const { rerender } = render(
      <ProductDetailPanel product={product} onConsult={noop} onClear={noop} />
    );
    fireEvent.click(screen.getByTestId("detail-buy-btn-AF-400-220V"));
    rerender(<ProductDetailPanel product={product} onConsult={() => {}} onClear={() => {}} />);

    expect(mockCheckout).toHaveBeenCalledTimes(1);
  });
});
