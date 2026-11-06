"use client";

import React from "react";
import { Product } from "@/types/catalog";
import { MessageSquare, Sparkles, CheckCircle, ShieldAlert } from "lucide-react";

export interface CatalogAndProductViewProps {
  products: Product[];
  selectedProduct: Product | null;
  onSelectProduct: (product: Product) => void;
}

export const CatalogAndProductView: React.FC<CatalogAndProductViewProps> = ({
  products,
  selectedProduct,
  onSelectProduct,
}) => {
  return (
    <section className="w-full">
      <div className="mb-6 flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-slate-800">Catálogo de Eletroportáteis Técnicos</h2>
          <p className="text-sm text-slate-500">Selecione um produto para tirar dúvidas com o Consultor IA ancorado no manual oficial.</p>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
        {products.map((product) => {
          const isSelected = selectedProduct?.sku === product.sku;
          const formattedPrice = new Intl.NumberFormat("pt-BR", {
            style: "currency",
            currency: "BRL",
          }).format(product.price);

          return (
            <div
              key={product.sku}
              data-testid={`product-card-${product.sku}`}
              className={`rounded-xl border bg-white p-5 shadow-sm transition-all duration-200 hover:shadow-md flex flex-col justify-between ${
                isSelected ? "border-blue-500 ring-2 ring-blue-100" : "border-slate-200"
              }`}
            >
              <div>
                <div className="flex items-center justify-between gap-2 mb-3">
                  <span className="text-xs font-mono font-semibold px-2 py-0.5 rounded bg-slate-100 text-slate-700">
                    {product.sku}
                  </span>
                  <span
                    className={`text-xs font-bold px-2 py-0.5 rounded ${
                      product.voltage === "220V"
                        ? "bg-amber-100 text-amber-800"
                        : product.voltage === "127V"
                        ? "bg-sky-100 text-sky-800"
                        : "bg-emerald-100 text-emerald-800"
                    }`}
                  >
                    {product.voltage}
                  </span>
                </div>

                <h3 className="font-semibold text-slate-900 text-base mb-1">
                  {product.name}
                </h3>
                <p className="text-xs text-slate-500 mb-3">{product.brand} · {product.category}</p>

                <p className="text-sm text-slate-600 line-clamp-2 mb-4">
                  {product.description}
                </p>

                <div className="flex items-baseline gap-2 mb-4">
                  <span className="text-xl font-bold text-slate-900">{formattedPrice}</span>
                  {product.stock_quantity > 0 ? (
                    <span className="text-xs text-emerald-600 flex items-center gap-1">
                      <CheckCircle className="w-3.5 h-3.5" /> Em estoque ({product.stock_quantity} un.)
                    </span>
                  ) : (
                    <span className="text-xs text-rose-600 flex items-center gap-1">
                      <ShieldAlert className="w-3.5 h-3.5" /> Esgotado
                    </span>
                  )}
                </div>
              </div>

              <button
                type="button"
                data-testid={`consult-ai-btn-${product.sku}`}
                onClick={() => onSelectProduct(product)}
                className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg text-sm font-semibold bg-blue-600 text-white hover:bg-blue-700 active:bg-blue-800 transition-colors"
              >
                <Sparkles className="w-4 h-4" />
                <span>Consultar IA sobre este item</span>
              </button>
            </div>
          );
        })}
      </div>
    </section>
  );
};
