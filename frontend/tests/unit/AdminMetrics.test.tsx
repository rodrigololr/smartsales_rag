import { afterEach, describe, expect, it } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { AdminMetricsDashboard } from "@/components/admin/AdminMetricsDashboard";

describe("UT-F05-01: painel do operador", () => {
  afterEach(() => {
    sessionStorage.clear();
  });

  it("autentica com admin-demo e exibe KPIs e dúvidas frequentes", async () => {
    render(<AdminMetricsDashboard />);

    fireEvent.change(screen.getByTestId("admin-token-input"), {
      target: { value: "admin-demo" },
    });
    fireEvent.click(screen.getByTestId("admin-token-submit"));

    expect(
      await screen.findByTestId("admin-dashboard", undefined, { timeout: 3000 })
    ).toBeInTheDocument();
    expect(screen.getByTestId("metric-ttft-p95")).toHaveTextContent("1460 ms");
    expect(screen.getByText("A forma de alumínio pode ir na airfryer?")).toBeInTheDocument();
    expect(screen.getByText("Checkouts confirmados")).toBeInTheDocument();
  });

  it("exibe erro amigável para token inválido", async () => {
    render(<AdminMetricsDashboard />);

    fireEvent.change(screen.getByTestId("admin-token-input"), {
      target: { value: "token-errado" },
    });
    fireEvent.click(screen.getByTestId("admin-token-submit"));

    expect(
      await screen.findByTestId("admin-error", undefined, { timeout: 3000 })
    ).toHaveTextContent(/Token administrativo inválido/i);
  });
});
