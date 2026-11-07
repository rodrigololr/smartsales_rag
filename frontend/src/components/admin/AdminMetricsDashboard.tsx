"use client";

import { useCallback, useEffect, useState } from "react";
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
import { ADMIN_DEMO_TOKEN, mockGetMetrics } from "@/lib/mock-api";
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
import { cn } from "@/lib/utils";

const TOKEN_STORAGE_KEY = "smartsales.admin-token";

function MetricCard({
  label,
  value,
  target,
  ok,
  progress,
  testId,
}: {
  label: string;
  value: string;
  target?: string;
  ok?: boolean;
  progress?: number;
  testId?: string;
}) {
  return (
    <Card className="gap-2 py-3" data-testid={testId}>
      <CardContent className="space-y-1.5 px-3">
        <p className="text-xs text-muted-foreground">{label}</p>
        <div className="flex items-end justify-between gap-2">
          <span className="text-xl font-bold text-foreground">{value}</span>
          {typeof ok === "boolean" ? (
            <Badge
              variant="outline"
              className={cn(
                "text-[10px]",
                ok
                  ? "border-emerald-200 bg-emerald-100 text-emerald-800"
                  : "border-amber-200 bg-amber-100 text-amber-800"
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
          <p className="text-[11px] text-muted-foreground">Meta: {target}</p>
        ) : null}
      </CardContent>
    </Card>
  );
}

export function AdminMetricsDashboard() {
  const [token, setToken] = useState("");
  const [tokenInput, setTokenInput] = useState("");
  const [metrics, setMetrics] = useState<MetricsSummary | null>(null);
  const [status, setStatus] = useState<"idle" | "loading" | "ready" | "error">("idle");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (adminToken: string) => {
    setStatus("loading");
    setError(null);
    try {
      const summary = await mockGetMetrics(adminToken);
      setMetrics(summary);
      setToken(adminToken);
      setStatus("ready");
      sessionStorage.setItem(TOKEN_STORAGE_KEY, adminToken);
    } catch (loadError) {
      sessionStorage.removeItem(TOKEN_STORAGE_KEY);
      setToken("");
      setMetrics(null);
      setStatus("error");
      setError(
        loadError instanceof Error
          ? loadError.message
          : "Não foi possível carregar as métricas."
      );
    }
  }, []);

  useEffect(() => {
    const stored =
      typeof window !== "undefined"
        ? sessionStorage.getItem(TOKEN_STORAGE_KEY)
        : null;
    if (!stored) return;
    const timer = setTimeout(() => {
      setTokenInput(stored);
      void load(stored);
    }, 0);
    return () => clearTimeout(timer);
  }, [load]);

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    if (!tokenInput.trim()) return;
    void load(tokenInput.trim());
  };

  const handleLogout = () => {
    sessionStorage.removeItem(TOKEN_STORAGE_KEY);
    setToken("");
    setTokenInput("");
    setMetrics(null);
    setStatus("idle");
    setError(null);
  };

  if (!token || status === "idle" || (status === "error" && !metrics)) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-muted/30 px-4 py-10">
        <Card className="w-full max-w-sm">
          <CardHeader className="items-center justify-items-center text-center">
            <div className="mb-1 flex size-12 items-center justify-center rounded-full bg-primary/10 text-primary">
              <ShieldCheck className="size-6" />
            </div>
            <CardTitle>Painel do Operador</CardTitle>
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
                data-testid="admin-token-input"
                autoComplete="current-password"
              />
              {error ? (
                <p className="text-xs text-rose-600" data-testid="admin-error">
                  {error}
                </p>
              ) : null}
              <Button
                type="submit"
                data-testid="admin-token-submit"
                disabled={!tokenInput.trim() || status === "loading"}
                className="w-full"
              >
                {status === "loading" ? (
                  <Loader2 className="animate-spin" />
                ) : (
                  <BarChart3 />
                )}
                Entrar no painel
              </Button>
              <p className="text-center text-[11px] text-muted-foreground">
                Ambiente de demonstração: use{" "}
                <span className="font-mono font-semibold">{ADMIN_DEMO_TOKEN}</span>
              </p>
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

  if (status === "loading" && !metrics) {
    return (
      <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
        <div className="mb-6 space-y-2">
          <Skeleton className="h-7 w-64" />
          <Skeleton className="h-4 w-48" />
        </div>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {Array.from({ length: 8 }).map((_, index) => (
            <Skeleton key={index} className="h-24 w-full" />
          ))}
        </div>
      </main>
    );
  }

  if (!metrics) return null;

  const topMax = Math.max(...metrics.top_questions.map((item) => item.count), 1);

  return (
    <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6 sm:py-8 lg:px-8" data-testid="admin-dashboard">
      <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-primary">
            UC09 · Operador / Lojista
          </p>
          <h1 className="text-2xl font-bold text-foreground">Métricas do Consultor IA</h1>
          <p className="text-sm text-muted-foreground">
            Janela de {formatDateTime(metrics.window.from)} até{" "}
            {formatDateTime(metrics.window.to)}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Link
            href="/"
            className={cn(buttonVariants({ variant: "outline", size: "sm" }), "gap-1.5")}
          >
            <ArrowLeft />
            Voltar à loja
          </Link>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => void load(token)}
            disabled={status === "loading"}
            className="gap-1.5"
          >
            <RefreshCw className={status === "loading" ? "animate-spin" : undefined} />
            Atualizar
          </Button>
          <Button type="button" variant="ghost" size="sm" onClick={handleLogout} className="gap-1.5">
            <LogOut />
            Sair
          </Button>
        </div>
      </div>

      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard label="Turnos no período" value={metrics.turns.toLocaleString("pt-BR")} />
        <MetricCard
          label="TTFT p50"
          value={formatMs(metrics.ttft_p50_ms)}
          target="≤ 1.500 ms"
          ok={metrics.ttft_p50_ms <= 1500}
        />
        <MetricCard
          label="TTFT p95"
          value={formatMs(metrics.ttft_p95_ms)}
          target="≤ 2.000 ms"
          ok={metrics.ttft_p95_ms <= 2000}
          testId="metric-ttft-p95"
        />
        <MetricCard
          label="Latência total p95"
          value={`${(metrics.total_latency_p95_ms / 1000).toFixed(1)} s`}
          target="≤ 8,0 s"
          ok={metrics.total_latency_p95_ms <= 8000}
        />
        <MetricCard
          label="Cache hit ratio"
          value={formatPercent(metrics.cache_hit_ratio)}
          target="≥ 30%"
          ok={metrics.cache_hit_ratio >= 0.3}
          progress={metrics.cache_hit_ratio * 100}
        />
        <MetricCard
          label="Taxa de erros 5xx"
          value={formatPercent(metrics.error_5xx_rate)}
          target="≤ 1%"
          ok={metrics.error_5xx_rate <= 0.01}
        />
        <MetricCard
          label="Aprovação (likes)"
          value={formatPercent(metrics.like_ratio)}
          target="≥ 80%"
          ok={metrics.like_ratio >= 0.8}
          progress={metrics.like_ratio * 100}
        />
        <MetricCard
          label="CTR dos cards"
          value={formatPercent(metrics.card_ctr)}
          target="≥ 10%"
          ok={metrics.card_ctr >= 0.1}
          progress={metrics.card_ctr * 100}
        />
        <MetricCard
          label="Checkouts confirmados"
          value={metrics.confirmed_checkouts.toLocaleString("pt-BR")}
          target="conversões rastreadas"
        />
      </section>

      <Card className="mt-6">
        <CardHeader>
          <CardTitle>Dúvidas mais frequentes</CardTitle>
          <CardDescription>
            Perguntas que mais consumiram turnos na janela monitorada.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ol className="space-y-3">
            {metrics.top_questions.map((item, index) => (
              <li key={item.question} className="space-y-1">
                <div className="flex items-start justify-between gap-3 text-sm">
                  <span className="flex gap-2 text-foreground">
                    <span className="font-mono text-xs text-muted-foreground">
                      {String(index + 1).padStart(2, "0")}
                    </span>
                    {item.question}
                  </span>
                  <span className="shrink-0 font-semibold tabular-nums text-foreground">
                    {item.count}
                  </span>
                </div>
                <div className="h-1.5 overflow-hidden rounded-full bg-muted">
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
