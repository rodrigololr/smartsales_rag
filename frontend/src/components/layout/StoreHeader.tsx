import Link from "next/link";
import { BarChart3, ShoppingBag } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/** `contained` aligns the bar with centered pages; the product page keeps it full-bleed. */
export function StoreHeader({ contained = false }: { contained?: boolean }) {
  return (
    <header className="sticky top-0 z-40 w-full border-b border-border bg-background/95 backdrop-blur">
      <div
        className={cn(
          "flex h-16 w-full items-center justify-between gap-2 px-4 sm:px-6",
          contained && "mx-auto max-w-7xl lg:px-8"
        )}
      >
        <Link href="/" className="flex min-w-0 items-center gap-2 sm:gap-3" aria-label="Voltar ao catálogo">
          <div className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-primary text-primary-foreground shadow-sm">
            <ShoppingBag aria-hidden className="size-5" />
          </div>
          <span className="truncate text-base font-extrabold tracking-tight text-foreground sm:text-lg">
            SmartSales<span className="hidden sm:inline"> RAG</span>
          </span>
          <Badge variant="secondary" className="hidden md:inline-flex">
            Assistente Especialista B2B
          </Badge>
        </Link>

        <Link
          href="/admin/metricas"
          className={cn(buttonVariants({ variant: "ghost", size: "sm" }), "h-10 min-w-10 gap-1.5 sm:h-8")}
          aria-label="Abrir painel de métricas"
        >
          <BarChart3 />
          <span className="hidden sm:inline">Métricas</span>
        </Link>
      </div>
    </header>
  );
}
