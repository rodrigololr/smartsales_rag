"use client";

import { useState } from "react";
import { MessageSquare, ShoppingCart, Star, X } from "lucide-react";
import type { Product } from "@/types/catalog";
import { createId, formatBRL } from "@/lib/format";
import { toPrimaryCard } from "@/lib/mock-data";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { CheckoutDialog } from "@/components/checkout/CheckoutDialog";
import { ProductThumb } from "@/components/shared/ProductThumb";

export interface ProductDetailPanelProps {
  product: Product;
  onConsult: () => void;
  onClear: () => void;
}

export function ProductDetailPanel({
  product,
  onConsult,
  onClear,
}: ProductDetailPanelProps) {
  const [sessionId] = useState(() => createId());
  const [checkoutOpen, setCheckoutOpen] = useState(false);
  const card = toPrimaryCard(product);

  return (
    <>
      <Card
        className="relative mb-6 overflow-hidden ring-primary/20"
        data-testid={`product-detail-${product.sku}`}
      >
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          onClick={onClear}
          aria-label="Fechar detalhes do produto"
          className="absolute top-2 right-2 z-10 text-muted-foreground"
        >
          <X />
        </Button>

        <CardContent className="grid gap-4 p-4 sm:p-5 md:grid-cols-[150px_1fr_auto] md:items-start">
          <ProductThumb
            product={product}
            className="h-32 w-full md:h-36 md:w-[150px]"
          />

          <div className="min-w-0 space-y-2">
            <div className="flex flex-wrap items-center gap-1.5">
              <Badge variant="secondary" className="font-mono font-semibold">
                {product.sku}
              </Badge>
              <Badge variant="outline">{product.category}</Badge>
              {product.rating ? (
                <span className="flex items-center gap-1 text-xs text-muted-foreground">
                  <Star className="size-3.5 fill-amber-400 text-amber-400" />
                  {product.rating.toFixed(1)}
                  {product.reviews_count ? ` (${product.reviews_count})` : ""}
                </span>
              ) : null}
            </div>

            <div>
              <h2 className="text-lg font-bold text-foreground sm:text-xl">
                {product.name}
              </h2>
              <p className="text-xs text-muted-foreground">
                {product.brand} · {product.subcategory}
              </p>
            </div>

            <p className="max-w-2xl text-sm text-muted-foreground">
              {product.description}
            </p>

            <div className="flex flex-wrap gap-1.5 pt-1">
              <Badge variant="outline">Voltagem {product.voltage}</Badge>
              {product.capacity_liters ? (
                <Badge variant="outline">{product.capacity_liters}L</Badge>
              ) : null}
              {product.power_watts ? (
                <Badge variant="outline">{product.power_watts} W</Badge>
              ) : null}
              <Badge variant="outline">{product.stock_quantity} em estoque</Badge>
            </div>
          </div>

          <div className="flex flex-col gap-2 border-t border-border pt-3 md:min-w-[190px] md:border-t-0 md:border-l md:pl-4 md:pt-0">
            <p className="text-2xl font-bold text-foreground">{formatBRL(product.price)}</p>
            <p className="text-xs text-emerald-600">
              Em estoque ({product.stock_quantity} un.)
            </p>
            <Button
              type="button"
              onClick={onConsult}
              data-testid={`detail-consult-btn-${product.sku}`}
              className="gap-1.5"
            >
              <MessageSquare />
              Perguntar ao consultor
            </Button>
            <Button
              type="button"
              variant="outline"
              onClick={() => setCheckoutOpen(true)}
              data-testid={`detail-buy-btn-${product.sku}`}
              className="gap-1.5"
            >
              <ShoppingCart />
              Comprar agora
            </Button>
          </div>
        </CardContent>
      </Card>

      <CheckoutDialog
        card={card}
        open={checkoutOpen}
        onOpenChange={setCheckoutOpen}
        sessionId={sessionId}
        messageId="product-detail"
      />
    </>
  );
}
