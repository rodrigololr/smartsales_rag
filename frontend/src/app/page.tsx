"use client";

import React, { useState } from "react";
import { Product } from "@/types/catalog";
import { CatalogAndProductView } from "@/components/catalog/CatalogAndProductView";
import { ContextualChatDrawer } from "@/components/chat/ContextualChatDrawer";
import { ShoppingBag, Bot, Filter } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

// Mock representativo alinhado ao seed data de UC08 e aos casos de teste TDD
const INITIAL_PRODUCTS: Product[] = [
  {
    sku: "AF-400-220V",
    name: "Airfryer SmartChef 4L",
    brand: "SmartChef",
    category: "Eletroportáteis",
    subcategory: "Fritadeiras Elétricas",
    price: 499.90,
    stock_quantity: 15,
    voltage: "220V",
    capacity_liters: 4.0,
    power_watts: 1500,
    image_url: "/images/airfryer-4l.jpg",
    description: "Fritadeira sem óleo com controle digital de temperatura e cesto antiaderente removível de 4 Litros.",
  },
  {
    sku: "AF-550-220V",
    name: "Airfryer SmartChef 5.5L Family",
    brand: "SmartChef",
    category: "Eletroportáteis",
    subcategory: "Fritadeiras Elétricas",
    price: 629.90,
    stock_quantity: 8,
    voltage: "220V",
    capacity_liters: 5.5,
    power_watts: 1800,
    image_url: "/images/airfryer-55l.jpg",
    description: "Capacidade expandida para famílias de até 6 pessoas, timer de 60 minutos e cesto quadrado.",
  },
  {
    sku: "CF-15B-127V",
    name: "Cafeteira Expresso Aroma Pro",
    brand: "AromaTech",
    category: "Eletroportáteis",
    subcategory: "Cafeteiras",
    price: 389.00,
    stock_quantity: 22,
    voltage: "127V",
    capacity_liters: 1.5,
    power_watts: 1050,
    image_url: "/images/cafeteira.jpg",
    description: "Bomba de 15 bar, bico vaporizador para leite e reservatório removível de 1.5 Litros.",
  },
];

export default function SmartSalesPage() {
  const [products] = useState<Product[]>(INITIAL_PRODUCTS);
  const [selectedProduct, setSelectedProduct] = useState<Product | null>(null);
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const [voltageFilter, setVoltageFilter] = useState<string>("ALL");

  const filteredProducts = products.filter((p) => {
    if (voltageFilter === "ALL") return true;
    return p.voltage === voltageFilter;
  });

  const handleSelectProduct = (product: Product) => {
    setSelectedProduct(product);
    setIsDrawerOpen(true);
  };

  const handleCloseDrawer = () => {
    setIsDrawerOpen(false);
  };

  return (
    <div className="flex min-h-screen flex-col bg-background">
      {/* Top Header */}
      <header className="sticky top-0 z-40 w-full border-b border-border bg-background/95 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
          <div className="flex items-center gap-2 sm:gap-3">
            <div className="flex size-10 items-center justify-center rounded-xl bg-primary text-primary-foreground shadow-sm">
              <ShoppingBag className="size-5" />
            </div>
            <div className="flex items-center gap-2">
              <span className="whitespace-nowrap text-base font-extrabold tracking-tight text-foreground sm:text-lg">
                SmartSales<span className="hidden sm:inline"> RAG</span>
              </span>
              <Badge variant="secondary" className="hidden sm:inline-flex">
                Assistente Especialista B2B
              </Badge>
            </div>
          </div>

          <div className="flex items-center gap-4">
            <div className="flex items-center gap-1 rounded-lg bg-muted p-1 text-xs text-muted-foreground">
              <Filter className="ml-1 size-3.5" />
              <Button
                type="button"
                variant="ghost"
                size="xs"
                aria-pressed={voltageFilter === "ALL"}
                onClick={() => setVoltageFilter("ALL")}
                className={cn(
                  "px-2 font-medium",
                  voltageFilter === "ALL"
                    ? "bg-background text-foreground shadow-xs hover:bg-background"
                    : "text-muted-foreground hover:text-foreground"
                )}
              >
                Todas
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="xs"
                aria-pressed={voltageFilter === "127V"}
                onClick={() => setVoltageFilter("127V")}
                className={cn(
                  "px-2 font-medium",
                  voltageFilter === "127V"
                    ? "bg-background text-sky-700 shadow-xs hover:bg-background"
                    : "text-muted-foreground hover:text-foreground"
                )}
              >
                127V
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="xs"
                aria-pressed={voltageFilter === "220V"}
                onClick={() => setVoltageFilter("220V")}
                className={cn(
                  "px-2 font-medium",
                  voltageFilter === "220V"
                    ? "bg-background text-amber-700 shadow-xs hover:bg-background"
                    : "text-muted-foreground hover:text-foreground"
                )}
              >
                220V
              </Button>
            </div>

            {selectedProduct && (
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setIsDrawerOpen(true)}
                className="hidden sm:inline-flex"
              >
                <Bot />
                <span>Abrir Chat IA</span>
              </Button>
            )}
          </div>
        </div>
      </header>

      {/* Main Container */}
      <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-8 sm:px-6 lg:px-8">
        <CatalogAndProductView
          products={filteredProducts}
          selectedProduct={selectedProduct}
          onSelectProduct={handleSelectProduct}
        />
      </main>

      {/* Contextual Side-Drawer */}
      <ContextualChatDrawer
        product={selectedProduct}
        isOpen={isDrawerOpen}
        onClose={handleCloseDrawer}
      />
    </div>
  );
}
