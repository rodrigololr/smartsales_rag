import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { findProduct } from "@/lib/mock-data";

const API = "http://middleend.test";
const SERVER_SESSION = "11111111-1111-4111-8111-111111111111";
const SERVER_MESSAGE = "33333333-3333-4333-8333-333333333333";
const airfryer = findProduct("AF-400-220V")!;

const sse = (events: [string, unknown][]): Response =>
  new Response(events.map(([name, data]) => `event: ${name}\ndata: ${JSON.stringify(data)}\n\n`).join(""), {
    status: 200,
    headers: { "Content-Type": "text/event-stream" },
  });

const apiError = (status: number, code: string): Response =>
  Response.json({ error: { code, message: code, trace_id: "t", details: {} } }, { status });

const recorded = (): Response =>
  Response.json(
    { feedback_id: "44444444-4444-4444-8444-444444444444", status: "RECORDED", recorded_at: "2026-11-20T10:00:00Z" },
    { status: 201 }
  );

/** Routes the real gateway calls; `feedbackResponses` are served in order. */
function stubGateway(
  feedbackResponses: (() => Response | Promise<Response>)[],
  { withMetadata = true }: { withMetadata?: boolean } = {}
) {
  const fetchMock = vi.fn(async (url: string, init?: RequestInit): Promise<Response> => {
    void init;
    if (url.endsWith("/api/v1/sessions")) {
      return Response.json({ session_id: SERVER_SESSION, restored: false, history: [], expires_in_seconds: 1800 }, { status: 201 });
    }
    if (url.endsWith("/api/v1/chat/stream")) {
      const metadata: [string, unknown][] = withMetadata
        ? [["metadata", { message_id: SERVER_MESSAGE, session_id: SERVER_SESSION, cache_hit: false, ttft_ms: 120 }]]
        : [];
      return sse([
        ...metadata,
        ["token", { delta: "Opera em 220V." }],
        ["done", { finish_reason: "stop", total_latency_ms: 300, tokens_used: 10 }],
      ]);
    }
    if (url.endsWith("/api/v1/feedback")) {
      const next = feedbackResponses.shift();
      if (!next) throw new Error("unexpected feedback call");
      return next();
    }
    throw new Error(`unexpected fetch ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

const feedbackBodies = (fetchMock: ReturnType<typeof stubGateway>): unknown[] =>
  fetchMock.mock.calls
    .filter(([url]) => url.endsWith("/api/v1/feedback"))
    .map(([, init]) => JSON.parse(String(init?.body)));

async function answerOneQuestion() {
  // API_BASE_URL is read at import time, so load the page after stubbing the env.
  const { ProductPageView } = await import("@/components/shop/ProductPageView");
  render(<ProductPageView product={airfryer} />);
  fireEvent.click(screen.getByTestId("quick-suggestion-0"));
  return screen.findByTestId(/^feedback-like-/);
}

beforeEach(() => {
  vi.resetModules();
  vi.stubEnv("NEXT_PUBLIC_API_BASE_URL", API);
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("UT-F03-02: feedback ligado ao POST /api/v1/feedback do gateway", () => {
  it("LIKE envia session_id e message_id do evento metadata e confirma", async () => {
    const fetchMock = stubGateway([recorded]);
    fireEvent.click(await answerOneQuestion());

    expect(await screen.findByText(/Obrigado pelo feedback/i)).toBeInTheDocument();
    expect(feedbackBodies(fetchMock)).toEqual([
      { session_id: SERVER_SESSION, message_id: SERVER_MESSAGE, rating: "LIKE" },
    ]);
    const [url, init] = fetchMock.mock.calls.find(([called]) => called.endsWith("/api/v1/feedback"))!;
    expect(url).toBe(`${API}/api/v1/feedback`);
    expect(init?.method).toBe("POST");
  });

  it("DISLIKE só é enviado depois de escolher o motivo", async () => {
    const fetchMock = stubGateway([recorded]);
    await answerOneQuestion();

    fireEvent.click(screen.getByTestId(/^feedback-dislike-/));
    expect(feedbackBodies(fetchMock)).toEqual([]);

    fireEvent.click(screen.getByTestId("feedback-reason-WRONG_VOLTAGE"));

    expect(await screen.findByText(/Obrigado pelo feedback/i)).toBeInTheDocument();
    expect(feedbackBodies(fetchMock)).toEqual([
      {
        session_id: SERVER_SESSION,
        message_id: SERVER_MESSAGE,
        rating: "DISLIKE",
        reason_category: "WRONG_VOLTAGE",
      },
    ]);
  });

  it("409 FEEDBACK_ALREADY_RECORDED aparece como já avaliada, sem erro", async () => {
    stubGateway([() => apiError(409, "FEEDBACK_ALREADY_RECORDED")]);
    fireEvent.click(await answerOneQuestion());

    expect(await screen.findByText(/já foi avaliada/i)).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("erro do gateway mostra mensagem amigável e reenvia a mesma escolha", async () => {
    const fetchMock = stubGateway([() => apiError(503, "SERVICE_UNAVAILABLE"), recorded]);
    await answerOneQuestion();
    fireEvent.click(screen.getByTestId(/^feedback-dislike-/));
    fireEvent.click(screen.getByTestId("feedback-reason-HALLUCINATION"));

    expect(await screen.findByRole("alert")).toHaveTextContent(/indisponível/i);

    fireEvent.click(screen.getByRole("button", { name: /Tentar enviar de novo/i }));

    expect(await screen.findByText(/Obrigado pelo feedback/i)).toBeInTheDocument();
    const [failed, retried] = feedbackBodies(fetchMock);
    expect(retried).toEqual(failed);
    expect(retried).toMatchObject({ rating: "DISLIKE", reason_category: "HALLUCINATION" });
  });

  it.each([
    [410, "SESSION_EXPIRED", /sessão expirou/i],
    [429, "RATE_LIMITED", /aguarde/i],
  ])("HTTP %i mostra mensagem específica", async (status, code, text) => {
    stubGateway([() => apiError(status, code)]);
    fireEvent.click(await answerOneQuestion());

    expect(await screen.findByRole("alert")).toHaveTextContent(text);
  });

  it("desabilita os botões enquanto envia", async () => {
    let release: (response: Response) => void = () => undefined;
    stubGateway([() => new Promise<Response>((resolve) => { release = resolve; })]);
    const like = await answerOneQuestion();

    fireEvent.click(like);

    await waitFor(() => expect(like).toBeDisabled());
    expect(screen.getByTestId(/^feedback-dislike-/)).toBeDisabled();
    release(recorded());
    expect(await screen.findByText(/Obrigado pelo feedback/i)).toBeInTheDocument();
  });

  it("sem metadata (sem message_id do servidor) não oferece feedback", async () => {
    const fetchMock = stubGateway([], { withMetadata: false });
    const { ProductPageView } = await import("@/components/shop/ProductPageView");
    render(<ProductPageView product={airfryer} />);
    fireEvent.click(screen.getByTestId("quick-suggestion-0"));

    expect(await screen.findByTestId("assistant-text")).toHaveTextContent("Opera em 220V.");
    await waitFor(() => expect(screen.queryByText(/Consultando manuais/i)).not.toBeInTheDocument());
    expect(screen.queryByTestId(/^feedback-bar-/)).not.toBeInTheDocument();
    expect(feedbackBodies(fetchMock)).toEqual([]);
  });
});
