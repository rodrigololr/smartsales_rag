"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { Search, X } from "lucide-react";
import type { Product } from "@/types/catalog";
import { API_BASE_URL } from "@/lib/chat-api";
import { StoreHeader } from "@/components/layout/StoreHeader";
import { ProductGrid } from "@/components/catalog/ProductGrid";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

const VOLTAGE_FILTERS = ["ALL", "127V", "220V"] as const;
type VoltageFilter = (typeof VOLTAGE_FILTERS)[number];

const filterLabel: Record<VoltageFilter, string> = {
  ALL: "Todas",
  "127V": "127V",
  "220V": "220V",
};

export interface CatalogViewProps {
  products: Product[];
  /** The gateway could not list the catalog: say so instead of an empty "no results". */
  unavailable?: boolean;
}

export function CatalogView({ products, unavailable = false }: CatalogViewProps) {
  const [voltageFilter, setVoltageFilter] = useState<VoltageFilter>("ALL");
  const [query, setQuery] = useState("");

  const filteredProducts = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    return products.filter((product) => {
      const matchesVoltage = voltageFilter === "ALL" || product.voltage === voltageFilter;
      const matchesQuery =
        !normalizedQuery ||
        [product.name, product.sku, product.brand, product.category, product.subcategory]
          .join(" ")
          .toLowerCase()
          .includes(normalizedQuery);
      return matchesVoltage && matchesQuery;
    });
  }, [products, query, voltageFilter]);

  return (
    <div className="flex min-h-screen flex-col bg-background">
      <StoreHeader contained />

      <main id="conteudo" className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 sm:px-6 sm:py-8 lg:px-8">
        <div className="mb-6">
          <h1 className="text-2xl font-bold tracking-tight text-foreground">Catálogo</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Abra um produto para ver os detalhes e tirar dúvidas com o Consultor IA.
          </p>
        </div>

        <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="relative w-full sm:max-w-sm">
            <Search aria-hidden className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Buscar por nome, SKU ou marca…"
              aria-label="Buscar produtos no catálogo"
              className="bg-card pl-9 pr-9"
            />
            {query ? (
              <Button
                type="button"
                variant="ghost"
                size="icon-xs"
                onClick={() => setQuery("")}
                aria-label="Limpar busca"
                className="absolute top-1/2 right-1 size-7 -translate-y-1/2 text-muted-foreground"
              >
                <X />
              </Button>
            ) : null}
          </div>

          <div
            role="group"
            aria-labelledby="filtro-voltagem"
            className="flex w-fit items-center gap-1 rounded-lg bg-muted p-1 text-xs text-muted-foreground"
          >
            <span id="filtro-voltagem" className="px-1.5 font-medium">
              Voltagem
            </span>
            {VOLTAGE_FILTERS.map((filter) => (
              <Button
                key={filter}
                type="button"
                variant="ghost"
                size="sm"
                aria-pressed={voltageFilter === filter}
                onClick={() => setVoltageFilter(filter)}
                className={cn(
                  "px-2 font-medium",
                  voltageFilter === filter
                    ? "bg-background text-foreground shadow-xs hover:bg-background"
                    : "text-muted-foreground hover:text-foreground"
                )}
              >
                {filterLabel[filter]}
              </Button>
            ))}
          </div>
        </div>

        {unavailable ? (
          <p
            role="alert"
            data-testid="catalog-error"
            className="rounded-2xl border border-rose-200 bg-rose-50 p-6 text-center text-sm text-rose-800"
          >
            O catálogo está indisponível agora.{" "}
            <Link href="/" prefetch={false} className="font-medium underline underline-offset-2">
              Tentar de novo
            </Link>
          </p>
        ) : (
          <>
            <p role="status" className="mb-3 text-xs text-muted-foreground">
              {filteredProducts.length === 1
                ? "1 produto"
                : `${filteredProducts.length} produtos`}
              {filteredProducts.length !== products.length ? ` de ${products.length}` : ""}
            </p>
            <ProductGrid
              products={filteredProducts}
              onClearFilters={() => {
                setQuery("");
                setVoltageFilter("ALL");
              }}
            />
          </>
        )}
      </main>

      <footer className="border-t border-border bg-muted/30 py-4 pb-[max(1rem,env(safe-area-inset-bottom))]">
        <div className="mx-auto flex max-w-7xl flex-col items-center justify-between gap-2 px-4 text-center text-xs text-muted-foreground sm:flex-row sm:px-6 sm:text-left lg:px-8">
          <span>
            SmartSales RAG ·{" "}
            {API_BASE_URL ? "Consultor conectado ao RAG dos manuais" : "MVP demonstrativo com dados mockados"}
          </span>
          <span>Manuais oficiais · Citações verificáveis · Checkout simulado</span>
        </div>
      </footer>
    </div>
  );
}
