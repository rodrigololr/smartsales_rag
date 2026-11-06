import { Coffee, Flame, Package, ShoppingBag } from "lucide-react";
import type { Product } from "@/types/catalog";
import { cn } from "@/lib/utils";

type ThumbProduct = Pick<Product, "name" | "subcategory">;

const renderIcon = (product: ThumbProduct) => {
  if (product.subcategory === "Cafeteiras") {
    return <Coffee className="size-8" strokeWidth={1.5} />;
  }
  if (
    product.subcategory.includes("Airfryer") ||
    product.subcategory.includes("Fritadeiras")
  ) {
    return <Flame className="size-8" strokeWidth={1.5} />;
  }
  if (product.subcategory.startsWith("Acessórios")) {
    return <Package className="size-8" strokeWidth={1.5} />;
  }
  return <ShoppingBag className="size-8" strokeWidth={1.5} />;
};

export function ProductThumb({
  product,
  className,
}: {
  product: ThumbProduct;
  className?: string;
}) {
  return (
    <div
      aria-hidden="true"
      className={cn(
        "flex items-center justify-center rounded-xl bg-gradient-to-br from-primary/15 via-primary/5 to-muted text-primary ring-1 ring-primary/10",
        className
      )}
    >
      {renderIcon(product)}
    </div>
  );
}
