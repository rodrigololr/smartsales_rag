"use client";

import React, { useState } from "react";
import { Product } from "@/types/catalog";
import { CatalogAndProductView } from "@/components/catalog/CatalogAndProductView";
import { ContextualChatDrawer } from "@/components/chat/ContextualChatDrawer";
import { ShoppingBag, Bot, Zap, Filter } from "lucide-react";

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
    <div className="min-h-screen flex flex-col bg-slate-50">
      {/* Top Header */}
      <header className="sticky top-0 z-40 w-full border-b border-slate-200 bg-white/95 backdrop-blur">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-blue-600 flex items-center justify-center text-white shadow-sm">
              <ShoppingBag className="w-5 h-5" />
            </div>
            <div>
              <span className="font-extrabold text-lg text-slate-900 tracking-tight">SmartSales RAG</span>
              <span className="hidden sm:inline-block ml-2 text-xs font-medium px-2 py-0.5 rounded bg-blue-50 text-blue-700 border border-blue-200">
                Assistente Especialista B2B
              </span>
            </div>
          </div>

          <div className="flex items-center gap-4">
            <div className="flex items-center gap-1.5 text-xs text-slate-600 bg-slate-100 p-1 rounded-lg">
              <Filter className="w-3.5 h-3.5 text-slate-400 ml-1" />
              <button
                type="button"
                onClick={() => setVoltageFilter("ALL")}
                className={`px-2 py-1 rounded font-medium transition-colors ${
                  voltageFilter === "ALL" ? "bg-white text-slate-900 shadow-xs" : "text-slate-500 hover:text-slate-900"
                }`}
              >
                Todas
              </button>
              <button
                type="button"
                onClick={() => setVoltageFilter("127V")}
                className={`px-2 py-1 rounded font-medium transition-colors ${
                  voltageFilter === "127V" ? "bg-white text-sky-700 shadow-xs" : "text-slate-500 hover:text-slate-900"
                }`}
              >
                127V
              </button>
              <button
                type="button"
                onClick={() => setVoltageFilter("220V")}
                className={`px-2 py-1 rounded font-medium transition-colors ${
                  voltageFilter === "220V" ? "bg-white text-amber-700 shadow-xs" : "text-slate-500 hover:text-slate-900"
                }`}
              >
                220V
              </button>
            </div>

            {selectedProduct && (
              <button
                type="button"
                onClick={() => setIsDrawerOpen(true)}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-blue-50 text-blue-700 border border-blue-200 hover:bg-blue-100 transition-colors"
              >
                <Bot className="w-4 h-4" />
                <span>Abrir Chat IA</span>
              </button>
            )}
          </div>
        </div>
      </header>

      {/* Main Container */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8">
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
