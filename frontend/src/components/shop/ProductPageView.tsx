"use client";

import { useState } from "react";
import Link from "next/link";
import { ChevronRight, Sparkles, Star } from "lucide-react";
import type { Product } from "@/types/catalog";
import { useChatSession } from "@/hooks/use-chat-session";
import { formatNumber, specsJsonRows, voltageBadgeClass } from "@/lib/format";
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
  rows.push(...specsJsonRows(product.specs_json));
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

        <main id="conteudo" className="mx-auto w-full min-w-0 max-w-[1440px] flex-1 px-4 pt-5 pb-24 sm:px-6 lg:px-8 lg:pb-8">
          <nav aria-label="Trilha de navegação" className="mb-4 text-xs text-muted-foreground">
            <ol className="flex flex-wrap items-center gap-1">
              <li>
                <Link href="/" className="underline-offset-2 hover:text-foreground hover:underline">Catálogo</Link>
              </li>
              <li aria-hidden="true"><ChevronRight className="size-3" /></li>
              <li>{product.category}</li>
              <li aria-hidden="true"><ChevronRight className="size-3" /></li>
              <li aria-current="page" className="text-foreground">{product.subcategory}</li>
            </ol>
          </nav>

          {/* Mobile reads title → price/buy → details; desktop keeps gallery | details | buy box. */}
          <div className="grid items-start gap-x-6 gap-y-5 md:grid-cols-2 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_260px]">
            <div className="md:row-span-2 xl:row-span-2">
              <ProductGallery product={product} />
            </div>

            <div className="min-w-0 space-y-2">
              <h1 className="text-2xl leading-tight font-semibold text-foreground">{product.name}</h1>
              <p className="text-sm text-muted-foreground">
                Marca: <span className="font-medium text-foreground">{product.brand}</span>
              </p>
              {product.rating ? (
                <p className="flex flex-wrap items-center gap-1.5 text-sm text-muted-foreground">
                  <span className="sr-only">
                    Avaliação {formatNumber(product.rating)} de 5
                  </span>
                  <span aria-hidden="true" className="font-semibold tabular-nums text-foreground">
                    {formatNumber(product.rating)}
                  </span>
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
                  {product.reviews_count ? (
                    <span>({formatNumber(product.reviews_count, 0)} avaliações)</span>
                  ) : null}
                </p>
              ) : null}
              <Badge variant="outline" className={cn("font-semibold", voltageBadgeClass(product.voltage))}>
                {product.voltage}
              </Badge>
            </div>

            <ProductBuyBox product={product} />

            <div className="min-w-0 space-y-5 md:col-span-2 xl:col-span-1 xl:col-start-2 xl:row-start-2">
              <section aria-labelledby="ficha-tecnica">
                <h2 id="ficha-tecnica" className="mb-2 text-base font-semibold text-foreground">
                  Ficha técnica
                </h2>
                <table className="w-full border-t border-border text-sm" data-testid="product-specs">
                  <tbody>
                    {specRows(product).map(([label, value]) => (
                      <tr key={label} className="border-b border-border/60 last:border-b-0">
                        <th scope="row" className="w-1/2 py-2 pr-3 text-left align-top font-medium text-foreground">
                          {label}
                        </th>
                        <td className="py-2 text-muted-foreground">{value}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </section>

              {product.description || product.features?.length ? (
                <section aria-labelledby="sobre-item">
                  <h2 id="sobre-item" className="mb-2 text-base font-semibold text-foreground">
                    Sobre este item
                  </h2>
                  <ul className="max-w-prose list-disc space-y-1 pl-5 text-sm text-muted-foreground">
                    {product.description ? <li>{product.description}</li> : null}
                    {(product.features ?? []).map((feature) => (
                      <li key={feature}>{feature}</li>
                    ))}
                  </ul>
                </section>
              ) : null}
            </div>
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
