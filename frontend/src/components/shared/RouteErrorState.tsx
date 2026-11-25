"use client";

import { useEffect } from "react";
import Link from "next/link";
import { ArrowLeft, RefreshCw, ShieldAlert } from "lucide-react";
import { StoreHeader } from "@/components/layout/StoreHeader";
import { Button, buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export interface RouteErrorStateProps {
  error: unknown;
  retry: () => void;
  title: string;
  description: string;
}

/** Fallback of the route `error.tsx` boundaries: plain message, retry and a way back. */
export function RouteErrorState({ error, retry, title, description }: RouteErrorStateProps) {
  useEffect(() => {
    console.error("route_render_failed", error);
  }, [error]);

  return (
    <div className="flex min-h-screen flex-col bg-background">
      <StoreHeader contained />
      <main id="conteudo" className="flex flex-1 items-center justify-center px-4 py-12">
        <div role="alert" className="flex max-w-md flex-col items-center gap-3 text-center" data-testid="route-error">
          <div className="flex size-12 items-center justify-center rounded-full bg-danger/10 text-danger">
            <ShieldAlert aria-hidden className="size-6" />
          </div>
          <h1 className="text-xl font-semibold text-foreground">{title}</h1>
          <p className="text-sm text-muted-foreground">{description}</p>
          <div className="mt-2 flex flex-wrap justify-center gap-2">
            <Button type="button" onClick={() => retry()} className="gap-1.5">
              <RefreshCw />
              Tentar novamente
            </Button>
            <Link href="/" className={cn(buttonVariants({ variant: "outline" }), "gap-1.5")}>
              <ArrowLeft />
              Voltar ao catálogo
            </Link>
          </div>
        </div>
      </main>
    </div>
  );
}
