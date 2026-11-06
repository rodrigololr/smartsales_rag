"use client";

import { useState } from "react";
import { ShoppingCart } from "lucide-react";
import type { ProductCardData, RecommendationType } from "@/types/chat";
import { formatBRL, marketplaceLabel, voltageBadgeClass } from "@/lib/format";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { CheckoutDialog } from "@/components/checkout/CheckoutDialog";
import { ProductThumb } from "@/components/shared/ProductThumb";
import { cn } from "@/lib/utils";

const toneByType: Record<RecommendationType, { card: string; badge: string }> = {
  PRIMARY: {
    card: "border-sky-200 bg-sky-50/50",
    badge: "border-sky-200 bg-sky-100 text-sky-800",
  },
  UPSELL: {
    card: "border-violet-200 bg-violet-50/50",
    badge: "border-violet-200 bg-violet-100 text-violet-800",
  },
  CROSS_SELL: {
    card: "border-emerald-200 bg-emerald-50/50",
    badge: "border-emerald-200 bg-emerald-100 text-emerald-800",
  },
};

const subcategoryOf = (card: ProductCardData): string => {
  if (card.name.toLowerCase().includes("cafeteira")) return "Cafeteiras";
  if (card.name.toLowerCase().includes("kit")) return "Acessórios";
  return "Fritadeiras Elétricas";
};

function RecommendationCard({
  card,
  onBuy,
}: {
  card: ProductCardData;
  onBuy: (card: ProductCardData) => void;
}) {
  const tone = toneByType[card.recommendation_type];

  return (
    <Card
      data-testid={`recommendation-card-${card.sku}`}
      className={cn("w-[252px] shrink-0 snap-start gap-2 py-3 text-xs", tone.card)}
    >
      <CardContent className="flex flex-col gap-2 px-3">
        <Badge
          variant="outline"
          className={cn("h-auto w-fit py-0.5 text-[10px] font-semibold uppercase", tone.badge)}
        >
          {card.badge_label}
        </Badge>

        <div className="flex items-start gap-2.5">
          <ProductThumb
            product={{ name: card.name, subcategory: subcategoryOf(card) }}
            className="size-12 shrink-0"
          />
          <div className="min-w-0">
            <p className="line-clamp-2 text-sm font-semibold text-foreground">{card.name}</p>
            <p className="font-mono text-[10px] text-muted-foreground">{card.sku}</p>
          </div>
        </div>

        <p className="line-clamp-2 min-h-8 text-[11px] leading-relaxed text-muted-foreground">
          {card.justification}
        </p>

        <div className="flex items-center justify-between gap-2">
          <span className="text-base font-bold text-foreground">{formatBRL(card.price)}</span>
          <Badge variant="outline" className={voltageBadgeClass(card.voltage)}>
            {card.voltage}
          </Badge>
        </div>

        <p className="text-[11px] font-medium text-emerald-600">
          Em estoque ({card.stock_quantity} un.)
        </p>

        <Button
          type="button"
          size="sm"
          data-testid={`buy-now-btn-${card.sku}`}
          onClick={() => onBuy(card)}
          className="mt-1 w-full gap-1.5"
        >
          <ShoppingCart />
          Comprar na {marketplaceLabel(card.marketplace)}
        </Button>
      </CardContent>
    </Card>
  );
}

export interface ProductRecommendationCarouselProps {
  products: ProductCardData[];
  sessionId: string;
  messageId: string;
}

export function ProductRecommendationCarousel({
  products,
  sessionId,
  messageId,
}: ProductRecommendationCarouselProps) {
  const [selected, setSelected] = useState<ProductCardData | null>(null);

  if (!products.length) return null;

  return (
    <div className="space-y-1.5" data-testid="recommendation-carousel">
      <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
        Recomendações para você
      </p>

      <div className="-mx-1 flex snap-x snap-mandatory gap-2.5 overflow-x-auto px-1 pb-2">
        {products.map((card) => (
          <RecommendationCard key={card.sku} card={card} onBuy={setSelected} />
        ))}
      </div>

      <p className="text-[10px] text-muted-foreground">
        Preço e estoque são revalidados antes de abrir o marketplace.
      </p>

      <CheckoutDialog
        card={selected}
        open={selected !== null}
        onOpenChange={(open) => {
          if (!open) setSelected(null);
        }}
        sessionId={sessionId}
        messageId={messageId}
      />
    </div>
  );
}
