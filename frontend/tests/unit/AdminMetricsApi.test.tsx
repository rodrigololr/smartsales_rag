import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import type { MetricsSummary } from "@/types/chat";

const API = "http://middleend.test";
const TOKEN = "s3cr3t-admin";
const NOW = new Date("2026-11-20T12:00:00Z");

const summary = (overrides: Partial<MetricsSummary> = {}): MetricsSummary => ({
  window: { from: "2026-11-13T12:00:00Z", to: "2026-11-20T12:00:00Z" },
  turns: 120,
  ttft_p50_ms: 900,
  ttft_p95_ms: 2400,
  total_latency_p95_ms: 6100,
  cache_hit_ratio: 0.42,
  error_5xx_rate: 0.004,
  like_ratio: 0.86,
  card_ctr: 0.12,
  confirmed_checkouts: 17,
  top_questions: [{ question: "Posso usar forma de alumínio?", count: 9 }],
  ...overrides,
});

const apiError = (status: number, code: string): Response =>
  Response.json({ error: { code, message: code, trace_id: "t", details: {} } }, { status });

function stubMetrics(responses: (() => Response)[]) {
  const fetchMock = vi.fn(async (url: string, init?: RequestInit): Promise<Response> => {
    void init;
    if (!url.startsWith(`${API}/api/v1/metrics/summary`)) throw new Error(`unexpected fetch ${url}`);
    const next = responses.shift();
    if (!next) throw new Error("unexpected metrics call");
    return next();
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

const tokenSent = (fetchMock: ReturnType<typeof stubMetrics>, call: number): string | null =>
  new Headers(fetchMock.mock.calls[call][1]?.headers).get("X-Admin-Token");

async function renderDashboard() {
  const { AdminMetricsDashboard } = await import("@/components/admin/AdminMetricsDashboard");
  render(<AdminMetricsDashboard />);
}

function submitToken(token: string) {
  fireEvent.change(screen.getByTestId("admin-token-input"), { target: { value: token } });
  fireEvent.click(screen.getByTestId("admin-token-submit"));
}

beforeEach(() => {
  vi.resetModules();
  vi.stubEnv("NEXT_PUBLIC_API_BASE_URL", API);
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(NOW);
});

afterEach(() => {
  sessionStorage.clear();
  vi.useRealTimers();
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("UT-F04-03: /admin/metricas ligado ao GET /api/v1/metrics/summary", () => {
  it("401 pede o token de novo; o token certo vai no cabeçalho, nunca na URL", async () => {
    const fetchMock = stubMetrics([() => apiError(401, "UNAUTHORIZED"), () => Response.json(summary())]);
    await renderDashboard();
    expect(screen.queryByText(/admin-demo/)).not.toBeInTheDocument();

    submitToken("errado");
    expect(await screen.findByTestId("admin-error")).toHaveTextContent(/token.*(inválido|recusado)/i);
    expect(sessionStorage.getItem("smartsales.admin-token")).toBeNull();

    submitToken(TOKEN);
    expect(await screen.findByTestId("admin-dashboard")).toBeInTheDocument();

    expect(tokenSent(fetchMock, 0)).toBe("errado");
    expect(tokenSent(fetchMock, 1)).toBe(TOKEN);
    for (const [url] of fetchMock.mock.calls) expect(url).not.toContain(TOKEN);
    expect(sessionStorage.getItem("smartsales.admin-token")).toBe(TOKEN);
  });

  it("mostra os KPIs com indicador de meta e as dúvidas frequentes", async () => {
    stubMetrics([() => Response.json(summary())]);
    await renderDashboard();
    submitToken(TOKEN);
    await screen.findByTestId("admin-dashboard");

    expect(screen.getByTestId("metric-ttft-p50")).toHaveTextContent("Na meta");
    expect(screen.getByTestId("metric-ttft-p95")).toHaveTextContent("2.400 ms");
    expect(screen.getByTestId("metric-ttft-p95")).toHaveTextContent("Fora da meta");
    expect(screen.getByTestId("metric-total-latency-p95")).toHaveTextContent("Na meta");
    expect(screen.getByTestId("metric-cache-hit")).toHaveTextContent("42%");
    expect(screen.getByTestId("metric-cache-hit")).toHaveTextContent("Na meta");
    expect(screen.getByTestId("metric-confirmed-checkouts")).toHaveTextContent("17");
    expect(screen.getByTestId("metric-turns")).toHaveTextContent("120");
    expect(screen.getByText("Posso usar forma de alumínio?")).toBeInTheDocument();
  });

  it("o seletor de janela envia from/to e recarrega", async () => {
    const fetchMock = stubMetrics([() => Response.json(summary()), () => Response.json(summary({ turns: 900 }))]);
    await renderDashboard();
    submitToken(TOKEN);
    await screen.findByTestId("admin-dashboard");

    const first = new URL(fetchMock.mock.calls[0][0]);
    expect(first.searchParams.get("to")).toBe(NOW.toISOString());
    expect(first.searchParams.get("from")).toBe("2026-11-13T12:00:00.000Z");

    fireEvent.click(within(screen.getByTestId("admin-window")).getByRole("button", { name: "24h" }));

    expect(await screen.findByText("900")).toBeInTheDocument();
    const second = new URL(fetchMock.mock.calls[1][0]);
    expect(second.searchParams.get("from")).toBe("2026-11-19T12:00:00.000Z");
  });

  it("janela sem turnos mostra estado vazio", async () => {
    stubMetrics([() => Response.json(summary({ turns: 0, top_questions: [] }))]);
    await renderDashboard();
    submitToken(TOKEN);

    expect(await screen.findByTestId("admin-empty")).toHaveTextContent(/nenhum turno/i);
  });

  it("erro do gateway mantém o token e oferece tentar de novo", async () => {
    stubMetrics([() => apiError(503, "SERVICE_UNAVAILABLE"), () => Response.json(summary())]);
    await renderDashboard();
    submitToken(TOKEN);

    expect(await screen.findByTestId("admin-load-error")).toHaveTextContent(/indisponível/i);
    expect(sessionStorage.getItem("smartsales.admin-token")).toBe(TOKEN);
    fireEvent.click(screen.getByRole("button", { name: "Tentar novamente" }));
    expect(await screen.findByTestId("admin-dashboard")).toBeInTheDocument();
  });
});
