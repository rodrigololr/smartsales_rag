"use client";

import { useState } from "react";
import Image from "next/image";
import type { Product } from "@/types/catalog";
import { cn } from "@/lib/utils";

export function ProductGallery({ product }: { product: Product }) {
  const photos = [product.image_url, ...(product.gallery ?? [])];
  const [active, setActive] = useState(0);

  return (
    <div className="flex flex-col-reverse gap-3 sm:flex-row sm:items-start">
      {photos.length > 1 ? (
        <div className="flex gap-2 sm:flex-col" role="tablist" aria-label="Fotos do produto">
          {photos.map((photo, index) => (
            <button
              key={photo}
              type="button"
              role="tab"
              aria-selected={index === active}
              aria-label={`Foto ${index + 1} de ${photos.length}`}
              onClick={() => setActive(index)}
              onMouseEnter={() => setActive(index)}
              className={cn(
                "relative size-16 overflow-hidden rounded-lg border bg-white transition",
                index === active ? "border-primary ring-2 ring-primary/30" : "border-border hover:border-primary/50"
              )}
            >
              <Image src={photo} alt="" fill unoptimized sizes="64px" className="object-contain" />
            </button>
          ))}
        </div>
      ) : null}
      <div className="relative aspect-square w-full overflow-hidden rounded-2xl border border-border bg-white">
        <Image
          src={photos[active]}
          alt={product.name}
          fill
          unoptimized
          priority
          sizes="(max-width: 1024px) 100vw, 40vw"
          className="object-contain"
          data-testid="product-main-image"
        />
      </div>
    </div>
  );
}
