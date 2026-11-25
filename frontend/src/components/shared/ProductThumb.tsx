import Image from "next/image";
import { Coffee, Flame, Package, ShoppingBag } from "lucide-react";
import type { Product } from "@/types/catalog";
import { cn } from "@/lib/utils";

type ThumbProduct = Pick<Product, "name" | "subcategory"> & { image_url?: string };

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

/** Product photo, or a category icon while the catalog has no image for it. */
export function ProductThumb({
  product,
  className,
}: {
  product: ThumbProduct;
  className?: string;
}) {
  if (product.image_url) {
    return (
      <div className={cn("relative overflow-hidden rounded-xl bg-white ring-1 ring-border", className)}>
        <Image
          src={product.image_url}
          alt={product.name}
          fill
          unoptimized
          sizes="(max-width: 640px) 50vw, 25vw"
          className="object-contain"
        />
      </div>
    );
  }
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
