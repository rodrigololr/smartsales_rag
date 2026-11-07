import Link from "next/link";
import { CheckCircle, SearchX, ShieldAlert, Star } from "lucide-react";
import type { Product } from "@/types/catalog";
import { formatBRL, voltageBadgeClass } from "@/lib/format";
import { ProductThumb } from "@/components/shared/ProductThumb";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

export function ProductGrid({ products }: { products: Product[] }) {
  if (!products.length) {
    return (
      <div className="flex flex-col items-center gap-3 rounded-2xl border border-border py-12 text-center">
        <div className="flex size-12 items-center justify-center rounded-full bg-muted text-muted-foreground">
          <SearchX className="size-6" />
        </div>
        <p className="font-semibold text-foreground">Nenhum produto encontrado</p>
        <p className="text-sm text-muted-foreground">
          Ajuste a busca ou o filtro de voltagem para ver outros itens.
        </p>
      </div>
    );
  }

  return (
    <ul className="grid grid-cols-2 gap-3 sm:gap-5 md:grid-cols-3 xl:grid-cols-4">
      {products.map((product) => (
        <li key={product.sku}>
          <Link
            href={`/produto/${product.sku}`}
            data-testid={`product-card-${product.sku}`}
            className="group flex h-full flex-col overflow-hidden rounded-2xl border border-border bg-card transition hover:border-primary/40 hover:shadow-md focus-visible:ring-2 focus-visible:ring-primary focus-visible:outline-none"
          >
            <ProductThumb
              product={product}
              className="aspect-square w-full rounded-none ring-0 transition group-hover:scale-[1.02]"
            />
            <div className="flex flex-1 flex-col gap-1.5 border-t border-border p-3 sm:p-4">
              <p className="line-clamp-2 text-sm font-medium text-foreground group-hover:text-primary">
                {product.name}
              </p>
              {product.rating ? (
                <p className="flex items-center gap-1 text-xs text-muted-foreground">
                  <Star className="size-3.5 fill-amber-400 text-amber-400" />
                  {product.rating.toFixed(1)}
                  {product.reviews_count ? ` (${product.reviews_count})` : ""}
                </p>
              ) : null}
              <div className="mt-auto flex flex-wrap items-center justify-between gap-2 pt-1">
                <span className="text-lg font-bold text-foreground">{formatBRL(product.price)}</span>
                <Badge variant="outline" className={cn("text-[10px]", voltageBadgeClass(product.voltage))}>
                  {product.voltage}
                </Badge>
              </div>
              {product.stock_quantity > 0 ? (
                <span className="flex items-center gap-1 text-xs text-emerald-600">
                  <CheckCircle className="size-3.5" /> Em estoque
                </span>
              ) : (
                <span className="flex items-center gap-1 text-xs text-rose-600">
                  <ShieldAlert className="size-3.5" /> Esgotado
                </span>
              )}
            </div>
          </Link>
        </li>
      ))}
    </ul>
  );
}
