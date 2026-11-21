"use client";

import { useState } from "react";
import { ShoppingCart } from "lucide-react";
import type { ProductCardData, RecommendationType } from "@/types/chat";
import { formatBRL, hasVoltage, marketplaceLabel, voltageBadgeClass, voltageLabel } from "@/lib/format";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { CheckoutDialog, type ValidatedStock } from "@/components/checkout/CheckoutDialog";
import { ProductThumb } from "@/components/shared/ProductThumb";
import { cn } from "@/lib/utils";

const toneByType: Record<RecommendationType, { card: string; badge: string }> = {
  PRIMARY: {
    card: "border-sky-200 bg-sky-50/50 dark:border-sky-900 dark:bg-sky-950/30",
    badge: "border-sky-200 bg-sky-100 text-sky-800 dark:border-sky-800 dark:bg-sky-950 dark:text-sky-200",
  },
  UPSELL: {
    card: "border-violet-200 bg-violet-50/50 dark:border-violet-900 dark:bg-violet-950/30",
    badge: "border-violet-200 bg-violet-100 text-violet-800 dark:border-violet-800 dark:bg-violet-950 dark:text-violet-200",
  },
  CROSS_SELL: {
    card: "border-emerald-200 bg-emerald-50/50 dark:border-emerald-900 dark:bg-emerald-950/30",
    badge: "border-emerald-200 bg-emerald-100 text-emerald-800 dark:border-emerald-800 dark:bg-emerald-950 dark:text-emerald-200",
  },
};

/** Fallback seal when the backend sends no `badge_label`. */
const sealByType: Record<RecommendationType, string> = {
  PRIMARY: "Ideal",
  UPSELL: "Upgrade",
  CROSS_SELL: "Acessório",
};

const subcategoryOf = (card: ProductCardData): string => {
  if (card.name.toLowerCase().includes("cafeteira")) return "Cafeteiras";
  if (card.name.toLowerCase().includes("kit")) return "Acessórios";
  return "Fritadeiras Elétricas";
};

function RecommendationCard({
  card,
  canBuy,
  onBuy,
}: {
  card: ProductCardData;
  canBuy: boolean;
  onBuy: (card: ProductCardData) => void;
}) {
  const tone = toneByType[card.recommendation_type];
  const inStock = card.stock_quantity > 0;

  return (
    <Card
      data-testid={`recommendation-card-${card.sku}`}
      className={cn("w-[min(252px,80vw)] shrink-0 snap-start gap-2 py-3 text-xs", tone.card)}
    >
      <CardContent className="flex flex-col gap-2 px-3">
        <div className="flex items-start justify-between gap-2">
          <Badge
            variant="outline"
            className={cn("h-auto w-fit py-0.5 text-[10px] font-semibold", tone.badge)}
          >
            {card.badge_label || sealByType[card.recommendation_type]}
          </Badge>
          {/* Wrong voltage is the costliest mistake here, so the tension reads first. */}
          {hasVoltage(card.voltage) ? (
            <Badge
              variant="outline"
              data-testid={`voltage-${card.sku}`}
              className={cn("h-auto shrink-0 px-2 py-0.5 text-sm font-bold", voltageBadgeClass(card.voltage))}
            >
              {voltageLabel(card.voltage)}
            </Badge>
          ) : null}
        </div>

        <div className="flex items-start gap-2.5">
          <ProductThumb
            product={{ name: card.name, subcategory: subcategoryOf(card), image_url: card.image_url }}
            className="size-16 shrink-0"
          />
          <div className="min-w-0">
            <p className="line-clamp-2 text-sm font-semibold text-foreground">{card.name}</p>
            <p className="font-mono text-[11px] text-muted-foreground">{card.sku}</p>
          </div>
        </div>

        <p className="line-clamp-3 min-h-8 text-xs leading-relaxed text-muted-foreground">
          {card.justification}
        </p>

        <div className="flex items-baseline justify-between gap-2">
          <span className="text-base font-bold tabular-nums text-foreground">{formatBRL(card.price)}</span>
          {inStock ? (
            <span className="text-xs font-medium text-success">
              Em estoque ({card.stock_quantity} un.)
            </span>
          ) : (
            <span className="text-xs font-medium text-danger">Esgotado</span>
          )}
        </div>

        <Button
          type="button"
          size="sm"
          disabled={!inStock || !canBuy}
          data-testid={`buy-now-btn-${card.sku}`}
          onClick={() => onBuy(card)}
          className="mt-1 w-full gap-1.5"
        >
          <ShoppingCart />
          {/* Sold-out is never offered as a purchase (R03). */}
          {inStock ? `Comprar na ${marketplaceLabel(card.marketplace)}` : "Indisponível"}
        </Button>
      </CardContent>
    </Card>
  );
}

export interface ProductRecommendationCarouselProps {
  products: ProductCardData[];
  sessionId: string;
  /** Server `message_id` of the turn; `null` disables checkout (the gateway would answer 404). */
  messageId: string | null;
}

export function ProductRecommendationCarousel({
  products,
  sessionId,
  messageId,
}: ProductRecommendationCarouselProps) {
  const [selected, setSelected] = useState<ProductCardData | null>(null);
  // Price/stock re-validated by the checkout override the turn's snapshot (R09).
  const [validated, setValidated] = useState<Record<string, ValidatedStock>>({});

  if (!products.length) return null;

  return (
    <div className="space-y-1.5" data-testid="recommendation-carousel">
      <h3 className="text-xs font-semibold text-foreground">
        Recomendações para você
      </h3>

      <div className="-mx-1 flex snap-x snap-mandatory gap-2.5 overflow-x-auto px-1 pb-2">
        {products.map((card) => {
          const current = validated[card.sku];
          const shown = current
            ? { ...card, price: current.price, stock_quantity: current.stock }
            : card;
          return (
            <RecommendationCard
              key={`${card.recommendation_type}:${card.sku}`}
              card={shown}
              canBuy={messageId !== null}
              onBuy={setSelected}
            />
          );
        })}
      </div>

      <p className="text-[11px] text-muted-foreground">
        Preço e estoque são revalidados antes de abrir o marketplace.
      </p>

      {messageId !== null ? (
        <CheckoutDialog
          card={selected}
          open={selected !== null}
          onOpenChange={(open) => {
            if (!open) setSelected(null);
          }}
          sessionId={sessionId}
          messageId={messageId}
          onValidated={(sku, stock) =>
            setValidated((previous) => ({ ...previous, [sku]: stock }))
          }
        />
      ) : null}
    </div>
  );
}
