"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import {
  BarChart3,
  Bot,
  Filter,
  Search,
  ShoppingBag,
  X,
} from "lucide-react";
import type { Product } from "@/types/catalog";
import { CATALOG_PRODUCTS } from "@/lib/mock-data";
import { API_BASE_URL } from "@/lib/chat-api";
import { CatalogAndProductView } from "@/components/catalog/CatalogAndProductView";
import { ContextualChatDrawer } from "@/components/chat/ContextualChatDrawer";
import { ProductDetailPanel } from "@/components/shop/ProductDetailPanel";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

const VOLTAGE_FILTERS = ["ALL", "127V", "220V"] as const;
type VoltageFilter = (typeof VOLTAGE_FILTERS)[number];

const filterLabel: Record<VoltageFilter, string> = {
  ALL: "Todas",
  "127V": "127V",
  "220V": "220V",
};

export default function SmartSalesPage() {
  const [selectedProduct, setSelectedProduct] = useState<Product | null>(null);
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const [voltageFilter, setVoltageFilter] = useState<VoltageFilter>("ALL");
  const [query, setQuery] = useState("");

  const filteredProducts = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    return CATALOG_PRODUCTS.filter((product) => {
      const matchesVoltage =
        voltageFilter === "ALL" || product.voltage === voltageFilter;
      const matchesQuery =
        !normalizedQuery ||
        [product.name, product.sku, product.brand, product.category, product.subcategory]
          .join(" ")
          .toLowerCase()
          .includes(normalizedQuery);
      return matchesVoltage && matchesQuery;
    });
  }, [query, voltageFilter]);

  const handleSelectProduct = (product: Product) => {
    setSelectedProduct(product);
    setIsDrawerOpen(true);
  };

  const handleViewProduct = (product: Product) => {
    setSelectedProduct(product);
  };

  const handleCloseDrawer = () => {
    setIsDrawerOpen(false);
  };

  const clearFilters = () => {
    setQuery("");
    setVoltageFilter("ALL");
  };

  return (
    <div className="flex min-h-screen flex-col bg-background">
      {/* Top Header */}
      <header className="sticky top-0 z-40 w-full border-b border-border bg-background/95 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between gap-2 px-4 sm:px-6 lg:px-8">
          <div className="flex min-w-0 items-center gap-2 sm:gap-3">
            <div className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-primary text-primary-foreground shadow-sm">
              <ShoppingBag className="size-5" />
            </div>
            <span className="truncate text-base font-extrabold tracking-tight text-foreground sm:text-lg">
              SmartSales<span className="hidden sm:inline"> RAG</span>
            </span>
            <Badge variant="secondary" className="hidden md:inline-flex">
              Assistente Especialista B2B
            </Badge>
          </div>

          <div className="flex shrink-0 items-center gap-1">
            <Link
              href="/admin/metricas"
              className={cn(buttonVariants({ variant: "ghost", size: "sm" }), "gap-1.5")}
              aria-label="Abrir painel de métricas"
            >
              <BarChart3 />
              <span className="hidden sm:inline">Métricas</span>
            </Link>

            {selectedProduct ? (
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setIsDrawerOpen(true)}
                className="gap-1.5"
                aria-label="Abrir chat do consultor"
              >
                <Bot />
                <span className="hidden sm:inline">Abrir Chat IA</span>
              </Button>
            ) : null}
          </div>
        </div>
      </header>

      {/* Main Container */}
      <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 sm:px-6 sm:py-8 lg:px-8">
        <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="relative w-full sm:max-w-sm">
            <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Buscar por nome, SKU ou marca..."
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
                className="absolute top-1/2 right-1 -translate-y-1/2 text-muted-foreground"
              >
                <X />
              </Button>
            ) : null}
          </div>

          <div className="flex w-fit items-center gap-1 rounded-lg bg-muted p-1 text-xs text-muted-foreground">
            <Filter className="ml-1 size-3.5" />
            {VOLTAGE_FILTERS.map((filter) => (
              <Button
                key={filter}
                type="button"
                variant="ghost"
                size="xs"
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

        {selectedProduct ? (
          <ProductDetailPanel
            key={selectedProduct.sku}
            product={selectedProduct}
            onConsult={() => setIsDrawerOpen(true)}
            onClear={() => setSelectedProduct(null)}
          />
        ) : null}

        <CatalogAndProductView
          products={filteredProducts}
          selectedProduct={selectedProduct}
          onSelectProduct={handleSelectProduct}
          onViewProduct={handleViewProduct}
        />

        {filteredProducts.length === 0 ? (
          <div className="mt-4 flex justify-center">
            <Button type="button" variant="outline" onClick={clearFilters}>
              Limpar busca e filtros
            </Button>
          </div>
        ) : null}
      </main>

      <footer className="border-t border-border bg-muted/30 py-4">
        <div className="mx-auto flex max-w-7xl flex-col items-center justify-between gap-2 px-4 text-xs text-muted-foreground sm:flex-row sm:px-6 lg:px-8">
          <span>
            SmartSales RAG ·{" "}
            {API_BASE_URL ? "Consultor conectado ao RAG dos manuais" : "MVP demonstrativo com dados mockados"}
          </span>
          <span>Manuais oficiais · Citações verificáveis · Checkout simulado</span>
        </div>
      </footer>

      <ContextualChatDrawer
        key={selectedProduct?.sku ?? "empty"}
        product={selectedProduct}
        isOpen={isDrawerOpen}
        onClose={handleCloseDrawer}
      />
    </div>
  );
}
