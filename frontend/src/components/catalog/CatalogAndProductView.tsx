"use client";

import React from "react";
import { Product } from "@/types/catalog";
import { Sparkles, CheckCircle, ShieldAlert } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { cn } from "@/lib/utils";

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
      <div className="mb-6 flex flex-col justify-between gap-4 md:flex-row md:items-center">
        <div>
          <h2 className="text-xl font-bold text-foreground">Catálogo de Eletroportáteis Técnicos</h2>
          <p className="text-sm text-muted-foreground">
            Selecione um produto para tirar dúvidas com o Consultor IA ancorado no manual oficial.
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
        {products.map((product) => {
          const isSelected = selectedProduct?.sku === product.sku;
          const formattedPrice = new Intl.NumberFormat("pt-BR", {
            style: "currency",
            currency: "BRL",
          }).format(product.price);

          return (
            <Card
              key={product.sku}
              data-testid={`product-card-${product.sku}`}
              className={cn(
                "flex flex-col transition-all duration-200 hover:shadow-md",
                isSelected && "ring-2 ring-primary"
              )}
            >
              <CardHeader>
                <div className="flex items-center justify-between gap-2">
                  <Badge variant="secondary" className="font-mono font-semibold">
                    {product.sku}
                  </Badge>
                  <Badge
                    variant="outline"
                    className={cn(
                      product.voltage === "220V" &&
                        "border-amber-200 bg-amber-100 text-amber-800",
                      product.voltage === "127V" &&
                        "border-sky-200 bg-sky-100 text-sky-800",
                      product.voltage !== "220V" &&
                        product.voltage !== "127V" &&
                        "border-emerald-200 bg-emerald-100 text-emerald-800"
                    )}
                  >
                    {product.voltage}
                  </Badge>
                </div>
                <CardTitle className="text-base font-semibold">{product.name}</CardTitle>
                <CardDescription className="text-xs">
                  {product.brand} · {product.category}
                </CardDescription>
              </CardHeader>

              <CardContent className="flex flex-1 flex-col gap-4">
                <p className="line-clamp-2 text-sm text-muted-foreground">
                  {product.description}
                </p>

                <div className="mt-auto flex items-baseline gap-2">
                  <span className="text-xl font-bold text-foreground">{formattedPrice}</span>
                  {product.stock_quantity > 0 ? (
                    <span className="flex items-center gap-1 text-xs text-emerald-600">
                      <CheckCircle className="size-3.5" /> Em estoque ({product.stock_quantity} un.)
                    </span>
                  ) : (
                    <span className="flex items-center gap-1 text-xs text-rose-600">
                      <ShieldAlert className="size-3.5" /> Esgotado
                    </span>
                  )}
                </div>
              </CardContent>

              <CardFooter>
                <Button
                  type="button"
                  data-testid={`consult-ai-btn-${product.sku}`}
                  onClick={() => onSelectProduct(product)}
                  className="w-full"
                >
                  <Sparkles />
                  <span>Consultar IA sobre este item</span>
                </Button>
              </CardFooter>
            </Card>
          );
        })}
      </div>
    </section>
  );
};
