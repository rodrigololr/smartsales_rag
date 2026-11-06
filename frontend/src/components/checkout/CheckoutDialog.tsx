"use client";

import { useEffect, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Loader2,
  ShoppingCart,
} from "lucide-react";
import type {
  Checkout,
  CheckoutConflict,
  ProductCardData,
} from "@/types/chat";
import { formatBRL, marketplaceLabel } from "@/lib/format";
import { mockCheckout } from "@/lib/mock-api";
import { Button, buttonVariants } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

type CheckoutState =
  | { phase: "loading" }
  | { phase: "confirmed"; data: Checkout }
  | { phase: "conflict"; data: CheckoutConflict }
  | { phase: "error"; message: string };

export interface CheckoutDialogProps {
  card: ProductCardData | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  sessionId: string;
  messageId: string;
}

export function CheckoutDialog({
  card,
  open,
  onOpenChange,
  sessionId,
  messageId,
}: CheckoutDialogProps) {
  const [state, setState] = useState<CheckoutState>({ phase: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (!open || !card) return;
    const controller = new AbortController();

    mockCheckout(
      {
        session_id: sessionId,
        message_id: messageId,
        sku: card.sku,
        recommendation_type: card.recommendation_type,
        quantity: 1,
        displayed_price: card.price,
      },
      controller.signal
    )
      .then((result) => {
        if (result.status === "CONFIRMED") {
          setState({ phase: "confirmed", data: result });
        } else {
          setState({ phase: "conflict", data: result });
        }
      })
      .catch((error: unknown) => {
        if (error instanceof Error && error.name === "AbortError") return;
        setState({
          phase: "error",
          message:
            error instanceof Error
              ? error.message
              : "Não foi possível validar o checkout agora.",
        });
      });

    return () => controller.abort();
  }, [attempt, card, messageId, open, sessionId]);

  const handleOpenChange = (nextOpen: boolean) => {
    if (!nextOpen) setState({ phase: "loading" });
    onOpenChange(nextOpen);
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent
        className="sm:max-w-md"
        data-testid="checkout-dialog"
        showCloseButton={state.phase !== "loading"}
      >
        {state.phase === "loading" ? (
          <>
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <Loader2 className="size-4 animate-spin text-primary" />
                Validando estoque e preço
              </DialogTitle>
              <DialogDescription>
                Estamos confirmando disponibilidade e valor atuais antes de abrir o
                marketplace.
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-2 py-2">
              <Skeleton className="h-4 w-3/4" />
              <Skeleton className="h-4 w-1/2" />
              <Skeleton className="h-20 w-full" />
            </div>
          </>
        ) : null}

        {state.phase === "confirmed" ? (
          <div data-testid="checkout-confirmed">
            <DialogHeader>
              <div className="mb-1 flex size-10 items-center justify-center rounded-full bg-emerald-100 text-emerald-700">
                <CheckCircle2 className="size-5" />
              </div>
              <DialogTitle>Compra confirmada</DialogTitle>
              <DialogDescription>{state.data.message}</DialogDescription>
            </DialogHeader>

            <div className="my-2 space-y-2 rounded-lg border border-border bg-muted/40 p-3 text-sm">
              <div className="flex items-start justify-between gap-3">
                <span className="font-medium text-foreground">
                  {state.data.product_name}
                </span>
                <span className="rounded-md bg-muted px-1.5 py-0.5 text-xs font-semibold">
                  {state.data.voltage}
                </span>
              </div>
              <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs text-muted-foreground">
                <dt>Canal</dt>
                <dd className="text-right font-medium text-foreground">
                  {marketplaceLabel(state.data.marketplace)}
                </dd>
                <dt>Quantidade</dt>
                <dd className="text-right font-medium text-foreground">
                  {state.data.quantity}
                </dd>
                <dt>Preço unitário</dt>
                <dd className="text-right font-medium text-foreground">
                  {formatBRL(state.data.confirmed_unit_price)}
                </dd>
                <dt>Total</dt>
                <dd className="text-right font-semibold text-foreground">
                  {formatBRL(state.data.total_amount)}
                </dd>
                <dt>Estoque restante</dt>
                <dd className="text-right font-medium text-foreground">
                  {state.data.remaining_stock} un.
                </dd>
              </dl>
            </div>

            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => handleOpenChange(false)}>
                Fechar
              </Button>
              <a
                href={state.data.redirect_checkout_url}
                target="_blank"
                rel="noreferrer"
                data-testid="checkout-redirect-link"
                className={cn(buttonVariants(), "gap-1.5")}
              >
                <ShoppingCart />
                Abrir na {marketplaceLabel(state.data.marketplace)}
              </a>
            </DialogFooter>
          </div>
        ) : null}

        {state.phase === "conflict" ? (
          <div data-testid="checkout-conflict">
            <DialogHeader>
              <div className="mb-1 flex size-10 items-center justify-center rounded-full bg-amber-100 text-amber-700">
                <AlertTriangle className="size-5" />
              </div>
              <DialogTitle>
                {state.data.status === "OUT_OF_STOCK"
                  ? "Item esgotado"
                  : "Preço atualizado"}
              </DialogTitle>
              <DialogDescription>{state.data.message}</DialogDescription>
            </DialogHeader>

            <div className="my-2 grid grid-cols-2 gap-2 text-sm">
              <div className="rounded-lg border border-border p-2.5">
                <p className="text-xs text-muted-foreground">Preço atual</p>
                <p className="font-semibold text-foreground">
                  {formatBRL(state.data.current_price)}
                </p>
              </div>
              <div className="rounded-lg border border-border p-2.5">
                <p className="text-xs text-muted-foreground">Estoque atual</p>
                <p className="font-semibold text-foreground">
                  {state.data.current_stock} un.
                </p>
              </div>
            </div>

            <DialogFooter>
              <Button type="button" onClick={() => handleOpenChange(false)}>
                Entendi
              </Button>
            </DialogFooter>
          </div>
        ) : null}

        {state.phase === "error" ? (
          <div>
            <DialogHeader>
              <DialogTitle>Não foi possível validar</DialogTitle>
              <DialogDescription>{state.message}</DialogDescription>
            </DialogHeader>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => handleOpenChange(false)}>
                Fechar
              </Button>
              <Button type="button" onClick={() => {
                setState({ phase: "loading" });
                setAttempt((value) => value + 1);
              }}>
                Tentar novamente
              </Button>
            </DialogFooter>
          </div>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
