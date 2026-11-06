"use client";

import React, { useState } from "react";
import { Product } from "@/types/catalog";
import { StoreHeader } from "@/components/layout/StoreHeader";
import { CatalogAndProductView } from "@/components/catalog/CatalogAndProductView";
import { ContextualChatDrawer } from "@/components/chat/ContextualChatDrawer";

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
  const [searchQuery, setSearchQuery] = useState<string>("");

  const filteredProducts = products.filter((p) => {
    const matchesVoltage = voltageFilter === "ALL" || p.voltage === voltageFilter;
    const matchesQuery =
      !searchQuery.trim() ||
      p.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      p.sku.toLowerCase().includes(searchQuery.toLowerCase()) ||
      p.brand.toLowerCase().includes(searchQuery.toLowerCase());
    return matchesVoltage && matchesQuery;
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
      {/* Store Header isolado (EAP 4.9) */}
      <StoreHeader
        voltageFilter={voltageFilter}
        onVoltageChange={setVoltageFilter}
        searchQuery={searchQuery}
        onSearchChange={setSearchQuery}
        selectedProduct={selectedProduct}
        onOpenDrawer={() => setIsDrawerOpen(true)}
      />

      {/* Main Container */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <CatalogAndProductView
          products={filteredProducts}
          selectedProduct={selectedProduct}
          onSelectProduct={handleSelectProduct}
        />
      </main>

      {/* Contextual Side-Drawer com SSE integrado */}
      <ContextualChatDrawer
        product={selectedProduct}
        isOpen={isDrawerOpen}
        onClose={handleCloseDrawer}
        voltagePreference={voltageFilter}
      />
    </div>
  );
}
