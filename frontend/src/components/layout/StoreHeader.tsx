"use client";

import React from "react";
import { ShoppingBag, Bot, Filter, Search } from "lucide-react";
import { Product } from "@/types/catalog";

export interface StoreHeaderProps {
  voltageFilter: string;
  onVoltageChange: (voltage: string) => void;
  searchQuery: string;
  onSearchChange: (query: string) => void;
  selectedProduct: Product | null;
  onOpenDrawer: () => void;
}

export const StoreHeader: React.FC<StoreHeaderProps> = ({
  voltageFilter,
  onVoltageChange,
  searchQuery,
  onSearchChange,
  selectedProduct,
  onOpenDrawer,
}) => {
  return (
    <header className="sticky top-0 z-40 w-full border-b border-slate-200 bg-white/95 backdrop-blur shadow-xs">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between gap-4">
        {/* Logo / Marca */}
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-blue-600 flex items-center justify-center text-white shadow-sm">
            <ShoppingBag className="w-5 h-5" />
          </div>
          <div>
            <span className="font-extrabold text-lg text-slate-900 tracking-tight">
              SmartSales RAG
            </span>
            <span className="hidden sm:inline-block ml-2 text-xs font-medium px-2 py-0.5 rounded bg-blue-50 text-blue-700 border border-blue-200">
              Consultor IA Especialista
            </span>
          </div>
        </div>

        {/* Barra de Pesquisa */}
        <div className="flex-1 max-w-md hidden md:block">
          <div className="relative">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => onSearchChange(e.target.value)}
              placeholder="Buscar por produto, marca ou especificação..."
              className="w-full text-xs pl-9 pr-4 py-2 rounded-lg border border-slate-200 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all"
            />
          </div>
        </div>

        {/* Filtros e Ações */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1 text-xs text-slate-600 bg-slate-100 p-1 rounded-lg">
            <Filter className="w-3.5 h-3.5 text-slate-400 ml-1 hidden sm:inline-block" />
            <button
              type="button"
              onClick={() => onVoltageChange("ALL")}
              className={`px-2 py-1 rounded font-medium transition-colors ${
                voltageFilter === "ALL"
                  ? "bg-white text-slate-900 shadow-xs"
                  : "text-slate-500 hover:text-slate-900"
              }`}
            >
              Todas
            </button>
            <button
              type="button"
              onClick={() => onVoltageChange("127V")}
              className={`px-2 py-1 rounded font-medium transition-colors ${
                voltageFilter === "127V"
                  ? "bg-white text-sky-700 shadow-xs"
                  : "text-slate-500 hover:text-slate-900"
              }`}
            >
              127V
            </button>
            <button
              type="button"
              onClick={() => onVoltageChange("220V")}
              className={`px-2 py-1 rounded font-medium transition-colors ${
                voltageFilter === "220V"
                  ? "bg-white text-amber-700 shadow-xs"
                  : "text-slate-500 hover:text-slate-900"
              }`}
            >
              220V
            </button>
          </div>

          {selectedProduct && (
            <button
              type="button"
              onClick={onOpenDrawer}
              data-testid="header-open-drawer-btn"
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-blue-50 text-blue-700 border border-blue-200 hover:bg-blue-100 transition-colors"
            >
              <Bot className="w-4 h-4" />
              <span className="hidden sm:inline">Abrir Chat ({selectedProduct.sku})</span>
              <span className="sm:hidden">Chat</span>
            </button>
          )}
        </div>
      </div>
    </header>
  );
};
