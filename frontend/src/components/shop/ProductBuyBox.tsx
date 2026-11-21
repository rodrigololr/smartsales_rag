import { CheckCircle, ShieldAlert, ShoppingCart, Truck } from "lucide-react";
import type { Product } from "@/types/catalog";
import { formatBRL, marketplaceLabel, safeHttpUrl } from "@/lib/format";
import { checkoutUrlOf, marketplaceOf } from "@/lib/mock-data";
import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/**
 * Buy box of the product page. It links straight to the marketplace `checkout_url`:
 * `POST /checkout/mock` requires the `message_id` of a chat turn (CheckoutCreate), and
 * this box lives outside the chat. Price/stock come from the SQL product (R09); a sold-out
 * product shows as unavailable with no purchase link (R03).
 */
export function ProductBuyBox({ product }: { product: Product }) {
  const inStock = product.stock_quantity > 0;
  const marketplace = marketplaceLabel(marketplaceOf(product));
  const checkoutHref = safeHttpUrl(checkoutUrlOf(product));

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
      {inStock && checkoutHref ? (
        <a
          href={checkoutHref}
          target="_blank"
          rel="noopener noreferrer"
          data-testid={`buy-btn-${product.sku}`}
          className={cn(buttonVariants({ size: "lg" }), "gap-2")}
        >
          <ShoppingCart />
          Comprar na {marketplace}
        </a>
      ) : inStock ? (
        <p className="text-xs text-muted-foreground">
          Link de compra indisponível. Pergunte ao Consultor IA onde comprar este modelo.
        </p>
      ) : (
        <p className="text-xs text-muted-foreground">
          Indisponível no momento. Pergunte ao Consultor IA por um modelo equivalente em estoque.
        </p>
      )}
      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1.5 border-t border-border pt-3 text-xs text-muted-foreground">
        <dt className="flex items-center gap-1"><Truck className="size-3.5" /> Vendido por</dt>
        <dd className="text-foreground">{marketplace}</dd>
      </dl>
    </aside>
  );
}
