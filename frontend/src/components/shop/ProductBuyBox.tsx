"use client";

import { useMemo, useState } from "react";
import { CheckCircle, ShieldAlert, ShoppingCart, Truck } from "lucide-react";
import type { Product } from "@/types/catalog";
import { createId, formatBRL, marketplaceLabel } from "@/lib/format";
import { marketplaceOf, toPrimaryCard } from "@/lib/mock-data";
import { Button } from "@/components/ui/button";
import { CheckoutDialog } from "@/components/checkout/CheckoutDialog";

export function ProductBuyBox({ product, sessionId }: { product: Product; sessionId: string }) {
  const [checkoutOpen, setCheckoutOpen] = useState(false);
  // Stable identity: CheckoutDialog re-runs the checkout call whenever `card` changes.
  const card = useMemo(() => toPrimaryCard(product), [product]);
  const [messageId] = useState(createId);
  const inStock = product.stock_quantity > 0;

  return (
    <aside className="flex flex-col gap-3 rounded-2xl border border-border bg-card p-4 shadow-xs md:col-span-2 xl:col-span-1">
      <p className="text-3xl font-bold text-foreground">{formatBRL(product.price)}</p>
      {inStock ? (
        <p className="flex items-center gap-1.5 text-sm font-medium text-emerald-600">
          <CheckCircle className="size-4" /> Em estoque ({product.stock_quantity} un.)
        </p>
      ) : (
        <p className="flex items-center gap-1.5 text-sm font-medium text-rose-600">
          <ShieldAlert className="size-4" /> Esgotado
        </p>
      )}
      <Button
        type="button"
        size="lg"
        disabled={!inStock}
        onClick={() => setCheckoutOpen(true)}
        data-testid={`buy-btn-${product.sku}`}
        className="gap-2"
      >
        <ShoppingCart />
        Comprar na {marketplaceLabel(marketplaceOf(product))}
      </Button>
      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1.5 border-t border-border pt-3 text-xs text-muted-foreground">
        <dt className="flex items-center gap-1"><Truck className="size-3.5" /> Vendido por</dt>
        <dd className="text-foreground">{marketplaceLabel(marketplaceOf(product))}</dd>
      </dl>
      <CheckoutDialog
        card={card}
        open={checkoutOpen}
        onOpenChange={setCheckoutOpen}
        sessionId={sessionId}
        messageId={messageId}
      />
    </aside>
  );
}
