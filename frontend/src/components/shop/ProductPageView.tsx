"use client";

import { useState } from "react";
import Link from "next/link";
import { ChevronRight, Sparkles, Star } from "lucide-react";
import type { Product } from "@/types/catalog";
import { useChatSession } from "@/hooks/use-chat-session";
import { voltageBadgeClass } from "@/lib/format";
import { StoreHeader } from "@/components/layout/StoreHeader";
import { ProductAssistant } from "@/components/chat/ProductAssistant";
import { ContextualChatDrawer } from "@/components/chat/ContextualChatDrawer";
import { ProductGallery } from "@/components/shop/ProductGallery";
import { ProductBuyBox } from "@/components/shop/ProductBuyBox";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

function specRows(product: Product): [string, string][] {
  const rows: [string, string][] = [
    ["Marca", product.brand],
    ["Categoria", product.subcategory],
    ["Voltagem", product.voltage],
  ];
  if (product.power_watts) rows.push(["Potência", `${product.power_watts} W`]);
  if (product.capacity_liters) rows.push(["Capacidade", `${product.capacity_liters} L`]);
  rows.push(["Código (SKU)", product.sku]);
  return rows;
}

/** Product page with the consultant docked beside it (Rufus-style). */
export function ProductPageView({ product }: { product: Product }) {
  // One conversation shared by the docked panel (desktop) and the sheet (mobile).
  const chat = useChatSession(product);
  const [isAssistantOpen, setIsAssistantOpen] = useState(false);

  return (
    <div className="flex min-h-screen flex-col bg-background">
      <StoreHeader />

      {/* Assistant flush with the viewport edge (Rufus-style); only the product content is centered. */}
      <div className="flex w-full flex-1">
        <aside
          aria-label="Consultor IA do produto"
          className="sticky top-16 hidden h-[calc(100dvh-4rem)] w-[360px] shrink-0 border-r border-border lg:block xl:w-[400px]"
        >
          <ProductAssistant product={product} chat={chat} />
        </aside>

        <main className="mx-auto w-full min-w-0 max-w-[1440px] flex-1 px-4 py-5 sm:px-6 lg:px-8">
          <nav aria-label="Navegação" className="mb-4 flex flex-wrap items-center gap-1 text-xs text-muted-foreground">
            <Link href="/" className="hover:text-foreground hover:underline">Catálogo</Link>
            <ChevronRight className="size-3" />
            <span>{product.category}</span>
            <ChevronRight className="size-3" />
            <span className="text-foreground">{product.subcategory}</span>
          </nav>

          <div className="grid items-start gap-6 md:grid-cols-2 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_260px]">
            <ProductGallery product={product} />

            <section className="min-w-0 space-y-3">
              <h1 className="text-2xl leading-tight font-semibold text-foreground">{product.name}</h1>
              <p className="text-sm text-primary">Marca: {product.brand}</p>
              {product.rating ? (
                <p className="flex items-center gap-1.5 text-sm text-muted-foreground">
                  <span className="font-semibold text-foreground">{product.rating.toFixed(1)}</span>
                  <span className="flex" aria-hidden="true">
                    {Array.from({ length: 5 }, (_, index) => (
                      <Star
                        key={index}
                        className={cn(
                          "size-4",
                          index < Math.round(product.rating ?? 0)
                            ? "fill-amber-400 text-amber-400"
                            : "text-muted-foreground/40"
                        )}
                      />
                    ))}
                  </span>
                  {product.reviews_count ? <span>({product.reviews_count} avaliações)</span> : null}
                </p>
              ) : null}
              <Badge variant="outline" className={cn("font-semibold", voltageBadgeClass(product.voltage))}>
                {product.voltage}
              </Badge>

              <table className="w-full border-t border-border text-sm" data-testid="product-specs">
                <tbody>
                  {specRows(product).map(([label, value]) => (
                    <tr key={label}>
                      <th scope="row" className="w-36 py-1.5 pr-3 text-left font-semibold text-foreground">
                        {label}
                      </th>
                      <td className="py-1.5 text-muted-foreground">{value}</td>
                    </tr>
                  ))}
                </tbody>
              </table>

              <div className="border-t border-border pt-3">
                <h2 className="mb-2 text-base font-semibold text-foreground">Sobre este item</h2>
                <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
                  <li>{product.description}</li>
                  {(product.features ?? []).map((feature) => (
                    <li key={feature}>{feature}</li>
                  ))}
                </ul>
              </div>
            </section>

            <ProductBuyBox product={product} sessionId={chat.sessionId} />
          </div>
        </main>
      </div>

      <Button
        type="button"
        onClick={() => setIsAssistantOpen(true)}
        data-testid="open-assistant-btn"
        className="fixed right-4 bottom-4 z-30 gap-2 rounded-full shadow-lg lg:hidden"
        size="lg"
      >
        <Sparkles />
        Pergunte ao Consultor IA
      </Button>
      <ContextualChatDrawer
        product={product}
        chat={chat}
        isOpen={isAssistantOpen}
        onClose={() => setIsAssistantOpen(false)}
      />
    </div>
  );
}
