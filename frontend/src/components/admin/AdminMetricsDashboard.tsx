"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  BarChart3,
  Loader2,
  LogOut,
  RefreshCw,
  ShieldCheck,
} from "lucide-react";
import type { MetricsSummary } from "@/types/chat";
import {
  formatDateTime,
  formatMs,
  formatPercent,
} from "@/lib/format";
import { ADMIN_DEMO_TOKEN, MockApiError, mockGetMetrics } from "@/lib/mock-api";
import { ChatApiError, USE_REAL_API, getMetricsSummary } from "@/lib/chat-api";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { ThemeToggle } from "@/components/layout/ThemeToggle";
import { cn } from "@/lib/utils";

const TOKEN_STORAGE_KEY = "smartsales.admin-token";

const HOUR_MS = 3_600_000;
const WINDOWS = [
  { key: "24h", label: "24h", hours: 24 },
  { key: "7d", label: "7 dias", hours: 24 * 7 },
  { key: "30d", label: "30 dias", hours: 24 * 30 },
] as const;
type WindowKey = (typeof WINDOWS)[number]["key"];
const DEFAULT_WINDOW: WindowKey = "7d";

/** CLAUDE.md §2 SLA targets plus RNF06/RNF08. */
const TARGETS = {
  ttftP50Ms: 1500,
  ttftP95Ms: 2000,
  totalLatencyP95Ms: 8000,
  cacheHitRatio: 0.3,
  error5xxRate: 0.01,
  likeRatio: 0.8,
  cardCtr: 0.1,
} as const;

const UNAUTHORIZED_MESSAGE =
  "Token administrativo inválido ou recusado pelo gateway. Informe o token de novo.";
const LOAD_ERROR_BY_STATUS: Record<number, string> = {
  429: "Muitas consultas seguidas. Aguarde alguns segundos e tente de novo.",
};
const GENERIC_LOAD_ERROR =
  "O serviço de métricas está indisponível agora. Tente novamente em instantes.";

const statusOf = (error: unknown): number | null =>
  error instanceof ChatApiError || error instanceof MockApiError ? error.status : null;

const windowRange = (key: WindowKey): { from: string; to: string } => {
  const hours = WINDOWS.find((option) => option.key === key)?.hours ?? 24 * 7;
  const to = new Date();
  return { from: new Date(to.getTime() - hours * HOUR_MS).toISOString(), to: to.toISOString() };
};

const readStoredToken = (): string | null => {
  try {
    return sessionStorage.getItem(TOKEN_STORAGE_KEY);
  } catch {
    return null; // storage blocked: the operator just types the token again
  }
};

const storeToken = (token: string | null) => {
  try {
    if (token) sessionStorage.setItem(TOKEN_STORAGE_KEY, token);
    else sessionStorage.removeItem(TOKEN_STORAGE_KEY);
  } catch {
    // storage blocked: the token simply is not remembered for this tab
  }
};

function MetricCard({
  label,
  value,
  target,
  hint,
  ok,
  progress,
  testId,
  className,
}: {
  label: string;
  value: string;
  target?: string;
  /** Context line for counters that have no target. */
  hint?: string;
  ok?: boolean;
  progress?: number;
  testId?: string;
  className?: string;
}) {
  return (
    <Card className={cn("gap-2 py-3", className)} data-testid={testId}>
      <CardContent className="space-y-1.5 px-3">
        <p className="text-xs text-muted-foreground">{label}</p>
        <div className="flex flex-wrap items-end justify-between gap-x-2 gap-y-1">
          <span className="text-xl font-bold tabular-nums text-foreground">{value}</span>
          {typeof ok === "boolean" ? (
            <Badge
              variant="outline"
              className={cn(
                "text-[10px]",
                ok
                  ? "border-emerald-200 bg-emerald-100 text-emerald-800 dark:border-emerald-800 dark:bg-emerald-950 dark:text-emerald-200"
                  : "border-amber-200 bg-amber-100 text-amber-800 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200"
              )}
            >
              {ok ? "Na meta" : "Fora da meta"}
            </Badge>
          ) : null}
        </div>
        {typeof progress === "number" ? (
          <Progress value={Math.min(progress, 100)} aria-label={label} />
        ) : null}
        {target ? (
          <p className="text-xs text-muted-foreground">Meta: {target}</p>
        ) : null}
        {hint ? <p className="text-xs text-muted-foreground">{hint}</p> : null}
      </CardContent>
    </Card>
  );
}

export function AdminMetricsDashboard() {
  const [token, setToken] = useState<string | null>(null);
  const [tokenInput, setTokenInput] = useState("");
  const [windowKey, setWindowKey] = useState<WindowKey>(DEFAULT_WINDOW);
  const [metrics, setMetrics] = useState<MetricsSummary | null>(null);
  const [status, setStatus] = useState<"idle" | "loading" | "ready" | "error">("idle");
  const [authError, setAuthError] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  // Only the latest request may update the screen (fast window switches).
  const latestRequest = useRef(0);

  const load = useCallback(async (adminToken: string, key: WindowKey) => {
    const requestId = ++latestRequest.current;
    setStatus("loading");
    setLoadError(null);
    try {
      const summary = USE_REAL_API
        ? await getMetricsSummary(adminToken, windowRange(key))
        : await mockGetMetrics(adminToken);
      if (requestId !== latestRequest.current) return;
      setMetrics(summary);
      setStatus("ready");
    } catch (error) {
      if (requestId !== latestRequest.current) return;
      if (statusOf(error) === 401) {
        storeToken(null);
        setToken(null);
        setMetrics(null);
        setStatus("idle");
        setAuthError(UNAUTHORIZED_MESSAGE);
        return;
      }
      console.warn("admin_metrics_failed", statusOf(error));
      setStatus("error");
      setLoadError(LOAD_ERROR_BY_STATUS[statusOf(error) ?? 0] ?? GENERIC_LOAD_ERROR);
    }
  }, []);

  useEffect(() => {
    const stored = readStoredToken();
    if (!stored) return;
    const timer = setTimeout(() => {
      setToken(stored);
      void load(stored, DEFAULT_WINDOW);
    }, 0);
    return () => clearTimeout(timer);
  }, [load]);

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    const adminToken = tokenInput.trim();
    if (!adminToken) return;
    storeToken(adminToken);
    setToken(adminToken);
    setTokenInput("");
    setAuthError(null);
    void load(adminToken, windowKey);
  };

  const handleWindow = (key: WindowKey) => {
    setWindowKey(key);
    if (token) void load(token, key);
  };

  const handleLogout = () => {
    latestRequest.current++;
    storeToken(null);
    setToken(null);
    setTokenInput("");
    setMetrics(null);
    setStatus("idle");
    setAuthError(null);
    setLoadError(null);
  };

  if (!token) {
    return (
      <main id="conteudo" className="flex min-h-screen items-center justify-center bg-muted/30 px-4 py-10">
        <Card className="w-full max-w-sm">
          <CardHeader className="items-center justify-items-center text-center">
            <div className="mb-1 flex size-12 items-center justify-center rounded-full bg-primary/10 text-primary">
              <ShieldCheck aria-hidden className="size-6" />
            </div>
            <CardTitle role="heading" aria-level={1} className="text-lg">
              Painel do Operador
            </CardTitle>
            <CardDescription>
              Informe o token administrativo para acessar qualidade e conversão do RAG.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="space-y-3">
              <Input
                type="password"
                value={tokenInput}
                onChange={(event) => setTokenInput(event.target.value)}
                placeholder="X-Admin-Token"
                aria-label="Token administrativo"
                aria-invalid={authError ? true : undefined}
                data-testid="admin-token-input"
                autoComplete="off"
              />
              {authError ? (
                <p role="alert" className="text-xs text-danger" data-testid="admin-error">
                  {authError}
                </p>
              ) : null}
              <Button
                type="submit"
                data-testid="admin-token-submit"
                disabled={!tokenInput.trim()}
                className="w-full"
              >
                <BarChart3 />
                Entrar no painel
              </Button>
              {USE_REAL_API ? null : (
                <p className="text-center text-[11px] text-muted-foreground">
                  Ambiente de demonstração: use{" "}
                  <span className="font-mono font-semibold">{ADMIN_DEMO_TOKEN}</span>
                </p>
              )}
              <Link
                href="/"
                className={cn(buttonVariants({ variant: "ghost", size: "sm" }), "w-full gap-1.5")}
              >
                <ArrowLeft />
                Voltar à loja
              </Link>
            </form>
          </CardContent>
        </Card>
      </main>
    );
  }

  const header = (
    <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-foreground">Métricas do Consultor IA</h1>
        <p className="mt-1 text-sm text-muted-foreground" aria-live="polite">
          {metrics
            ? `Janela de ${formatDateTime(metrics.window.from)} até ${formatDateTime(metrics.window.to)}`
            : "Carregando a janela selecionada"}
        </p>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <ThemeToggle />
        <div
          role="group"
          aria-label="Janela de tempo"
          data-testid="admin-window"
          className="flex items-center gap-1 rounded-lg bg-muted p-1"
        >
          {WINDOWS.map((option) => (
            <Button
              key={option.key}
              type="button"
              variant="ghost"
              size="xs"
              aria-pressed={windowKey === option.key}
              onClick={() => handleWindow(option.key)}
              className={cn(
                "px-2 font-medium",
                windowKey === option.key
                  ? "bg-background text-foreground shadow-xs hover:bg-background"
                  : "text-muted-foreground hover:text-foreground"
              )}
            >
              {option.label}
            </Button>
          ))}
        </div>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => void load(token, windowKey)}
          disabled={status === "loading"}
          className="gap-1.5"
        >
          <RefreshCw className={status === "loading" ? "animate-spin" : undefined} />
          Atualizar
        </Button>
        <Link
          href="/"
          className={cn(buttonVariants({ variant: "outline", size: "sm" }), "gap-1.5")}
        >
          <ArrowLeft />
          Voltar à loja
        </Link>
        <Button type="button" variant="ghost" size="sm" onClick={handleLogout} className="gap-1.5">
          <LogOut />
          Sair
        </Button>
      </div>
    </div>
  );

  if (status === "error") {
    return (
      <main id="conteudo" className="mx-auto max-w-7xl px-4 py-6 sm:px-6 sm:py-8 lg:px-8">
        {header}
        <Card data-testid="admin-load-error" role="alert">
          <CardHeader>
            <CardTitle role="heading" aria-level={2}>Não foi possível carregar as métricas</CardTitle>
            <CardDescription>{loadError}</CardDescription>
          </CardHeader>
          <CardContent>
            <Button type="button" onClick={() => void load(token, windowKey)} className="gap-1.5">
              <RefreshCw />
              Tentar novamente
            </Button>
          </CardContent>
        </Card>
      </main>
    );
  }

  if (!metrics) {
    return (
      <main id="conteudo" className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8" aria-busy="true">
        {header}
        <p className="sr-only" role="status">
          <Loader2 /> Carregando métricas
        </p>
        <div className="grid grid-cols-2 gap-2 sm:gap-3 lg:grid-cols-3">
          {Array.from({ length: 9 }).map((_, index) => (
            <Skeleton key={index} className={cn("h-24 w-full", index === 0 && "col-span-2 lg:col-span-1")} />
          ))}
        </div>
      </main>
    );
  }

  if (metrics.turns === 0) {
    return (
      <main id="conteudo" className="mx-auto max-w-7xl px-4 py-6 sm:px-6 sm:py-8 lg:px-8" data-testid="admin-dashboard">
        {header}
        <Card data-testid="admin-empty">
          <CardHeader>
            <CardTitle role="heading" aria-level={2}>Nenhum turno registrado nesta janela</CardTitle>
            <CardDescription>
              Os indicadores aparecem depois das primeiras perguntas ao consultor. Escolha uma
              janela maior ou volte mais tarde.
            </CardDescription>
          </CardHeader>
        </Card>
      </main>
    );
  }

  const topMax = Math.max(...metrics.top_questions.map((item) => item.count), 1);

  return (
    <main id="conteudo" className="mx-auto max-w-7xl px-4 py-6 sm:px-6 sm:py-8 lg:px-8" data-testid="admin-dashboard">
      {header}

      <section aria-label="Indicadores do período" className="grid grid-cols-2 gap-2 sm:gap-3 lg:grid-cols-3">
        <MetricCard
          label="Turnos no período"
          value={metrics.turns.toLocaleString("pt-BR")}
          testId="metric-turns"
          className="col-span-2 lg:col-span-1"
        />
        <MetricCard
          label="TTFT p50"
          value={formatMs(metrics.ttft_p50_ms)}
          target="≤ 1,5 s (nominal)"
          ok={metrics.ttft_p50_ms <= TARGETS.ttftP50Ms}
          testId="metric-ttft-p50"
        />
        <MetricCard
          label="TTFT p95"
          value={formatMs(metrics.ttft_p95_ms)}
          target="≤ 2,0 s (teto de SLA)"
          ok={metrics.ttft_p95_ms <= TARGETS.ttftP95Ms}
          testId="metric-ttft-p95"
        />
        <MetricCard
          label="Latência total p95"
          value={`${(metrics.total_latency_p95_ms / 1000).toLocaleString("pt-BR", { maximumFractionDigits: 1 })} s`}
          target="≤ 8,0 s"
          ok={metrics.total_latency_p95_ms <= TARGETS.totalLatencyP95Ms}
          testId="metric-total-latency-p95"
        />
        <MetricCard
          label="Cache hit ratio"
          value={formatPercent(metrics.cache_hit_ratio)}
          target="≥ 30%"
          ok={metrics.cache_hit_ratio >= TARGETS.cacheHitRatio}
          progress={metrics.cache_hit_ratio * 100}
          testId="metric-cache-hit"
        />
        <MetricCard
          label="Taxa de erros 5xx"
          value={formatPercent(metrics.error_5xx_rate)}
          target="≤ 1%"
          ok={metrics.error_5xx_rate <= TARGETS.error5xxRate}
          testId="metric-5xx"
        />
        <MetricCard
          label="Aprovação (likes)"
          value={formatPercent(metrics.like_ratio)}
          target="≥ 80%"
          ok={metrics.like_ratio >= TARGETS.likeRatio}
          progress={metrics.like_ratio * 100}
          testId="metric-like-ratio"
        />
        <MetricCard
          label="CTR dos cards"
          value={formatPercent(metrics.card_ctr)}
          target="≥ 10%"
          ok={metrics.card_ctr >= TARGETS.cardCtr}
          progress={metrics.card_ctr * 100}
          testId="metric-card-ctr"
        />
        <MetricCard
          label="Checkouts confirmados"
          value={metrics.confirmed_checkouts.toLocaleString("pt-BR")}
          hint="Conversões rastreadas pelo checkout simulado"
          testId="metric-confirmed-checkouts"
        />
      </section>

      <Card className="mt-6">
        <CardHeader>
          <CardTitle role="heading" aria-level={2}>Dúvidas mais frequentes</CardTitle>
          <CardDescription>
            Perguntas que mais consumiram turnos na janela monitorada.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {metrics.top_questions.length ? null : (
            <p className="text-sm text-muted-foreground">Nenhuma pergunta registrada nesta janela.</p>
          )}
          <ol className="space-y-3">
            {metrics.top_questions.map((item, index) => (
              <li key={item.question} className="space-y-1">
                <div className="flex items-start justify-between gap-3 text-sm">
                  <span className="flex min-w-0 gap-2 text-foreground">
                    <span className="font-mono text-xs text-muted-foreground">
                      {String(index + 1).padStart(2, "0")}
                    </span>
                    {item.question}
                  </span>
                  <span className="shrink-0 font-semibold tabular-nums text-foreground">
                    {item.count}
                  </span>
                </div>
                <div aria-hidden="true" className="h-1.5 overflow-hidden rounded-full bg-muted">
                  <div
                    className="h-full rounded-full bg-primary"
                    style={{ width: `${(item.count / topMax) * 100}%` }}
                  />
                </div>
              </li>
            ))}
          </ol>
        </CardContent>
      </Card>
    </main>
  );
}
