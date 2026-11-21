"use client";

import { useEffect, useRef, useState } from "react";
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
import { formatBRL, marketplaceLabel, safeHttpUrl } from "@/lib/format";
import { MockApiError, mockCheckout } from "@/lib/mock-api";
import { ChatApiError, USE_REAL_API, postCheckout } from "@/lib/chat-api";
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

/** Price and stock the gateway just validated in SQL (R09). */
export interface ValidatedStock {
  price: number;
  stock: number;
}

const GENERIC_CHECKOUT_ERROR =
  "O checkout está indisponível no momento. Tente novamente em instantes.";

const CHECKOUT_ERROR_BY_STATUS: Record<number, string> = {
  404: "Este item não está mais disponível no catálogo. Peça ao consultor uma alternativa.",
  410: "Sua sessão expirou. Faça a pergunta de novo para receber recomendações atualizadas.",
  422: "O pedido não pôde ser validado pelo servidor. Tente novamente.",
  429: "Muitas tentativas seguidas. Aguarde alguns segundos e tente de novo.",
};

export const describeCheckoutError = (error: unknown): string =>
  ((error instanceof ChatApiError || error instanceof MockApiError) &&
    CHECKOUT_ERROR_BY_STATUS[error.status]) ||
  GENERIC_CHECKOUT_ERROR;

const requestCheckout = USE_REAL_API ? postCheckout : mockCheckout;

export interface CheckoutDialogProps {
  card: ProductCardData | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  sessionId: string;
  /** Server `message_id` of the turn that showed the card (SSE `metadata`). */
  messageId: string;
  /** Called on close with the price/stock the checkout validated, so the card can update. */
  onValidated?: (sku: string, validated: ValidatedStock) => void;
}

export function CheckoutDialog({
  card,
  open,
  onOpenChange,
  sessionId,
  messageId,
  onValidated,
}: CheckoutDialogProps) {
  const [state, setState] = useState<CheckoutState>({ phase: "loading" });
  // Every explicit user action (open, retry, accept new price) is one attempt = one POST.
  const [attempt, setAttempt] = useState(0);
  // Attempt already posted: re-runs of the effect (StrictMode, new props) never re-post,
  // because the gateway decrements stock on each CONFIRMED.
  const postedAttemptRef = useRef<number | null>(null);
  // Set only when the user accepts a PRICE_CHANGED: the next request carries the new price.
  const [acceptedPrice, setAcceptedPrice] = useState<number | null>(null);

  useEffect(() => {
    if (!open || !card || postedAttemptRef.current === attempt) return;
    postedAttemptRef.current = attempt;
    const isCurrent = () => postedAttemptRef.current === attempt;

    requestCheckout({
      session_id: sessionId,
      message_id: messageId,
      sku: card.sku,
      recommendation_type: card.recommendation_type,
      quantity: 1,
      displayed_price: acceptedPrice ?? card.price,
    })
      .then((result) => {
        if (!isCurrent()) return;
        if (result.status === "CONFIRMED") {
          setState({ phase: "confirmed", data: result });
        } else {
          setState({ phase: "conflict", data: result });
        }
      })
      .catch((error: unknown) => {
        if (!isCurrent()) return;
        console.warn("checkout_failed", error);
        setState({ phase: "error", message: describeCheckoutError(error) });
      });
  }, [acceptedPrice, attempt, card, messageId, open, sessionId]);

  const retry = (price: number | null) => {
    setState({ phase: "loading" });
    setAcceptedPrice(price);
    setAttempt((value) => value + 1);
  };

  const handleOpenChange = (nextOpen: boolean) => {
    if (!nextOpen) {
      if (state.phase === "confirmed") {
        onValidated?.(state.data.sku, {
          price: state.data.confirmed_unit_price,
          stock: state.data.remaining_stock,
        });
      } else if (state.phase === "conflict") {
        onValidated?.(state.data.sku, {
          price: state.data.current_price,
          stock: state.data.current_stock,
        });
      }
      setState({ phase: "loading" });
      setAcceptedPrice(null);
      // Drop a late answer of this attempt; the next open is a new attempt.
      postedAttemptRef.current = null;
      setAttempt((value) => value + 1);
    }
    onOpenChange(nextOpen);
  };

  const redirectHref =
    state.phase === "confirmed" ? safeHttpUrl(state.data.redirect_checkout_url) : null;

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
              <div className="mb-1 flex size-10 items-center justify-center rounded-full bg-success/10 text-success">
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
              {redirectHref ? (
                <a
                  href={redirectHref}
                  target="_blank"
                  rel="noopener noreferrer"
                  data-testid="checkout-redirect-link"
                  className={cn(buttonVariants(), "gap-1.5")}
                >
                  <ShoppingCart />
                  Abrir na {marketplaceLabel(state.data.marketplace)}
                </a>
              ) : null}
            </DialogFooter>
          </div>
        ) : null}

        {state.phase === "conflict" ? (
          <div data-testid="checkout-conflict">
            <DialogHeader>
              <div className="mb-1 flex size-10 items-center justify-center rounded-full bg-warning/10 text-warning">
                <AlertTriangle className="size-5" />
              </div>
              <DialogTitle>
                {state.data.status === "OUT_OF_STOCK"
                  ? "Item esgotado"
                  : "Preço atualizado"}
              </DialogTitle>
              <DialogDescription>
                {state.data.message}
                {state.data.status === "OUT_OF_STOCK"
                  ? " Peça ao consultor uma alternativa em estoque."
                  : " Confira o novo valor antes de seguir para o marketplace."}
              </DialogDescription>
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
              {state.data.status === "PRICE_CHANGED" ? (
                <>
                  <Button type="button" variant="outline" onClick={() => handleOpenChange(false)}>
                    Cancelar
                  </Button>
                  <Button type="button" onClick={() => retry(state.data.current_price)}>
                    Confirmar por {formatBRL(state.data.current_price)}
                  </Button>
                </>
              ) : (
                <Button type="button" onClick={() => handleOpenChange(false)}>
                  Entendi
                </Button>
              )}
            </DialogFooter>
          </div>
        ) : null}

        {state.phase === "error" ? (
          <div data-testid="checkout-error">
            <DialogHeader>
              <DialogTitle>Não foi possível validar</DialogTitle>
              <DialogDescription>{state.message}</DialogDescription>
            </DialogHeader>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => handleOpenChange(false)}>
                Fechar
              </Button>
              <Button type="button" onClick={() => retry(acceptedPrice)}>
                Tentar novamente
              </Button>
            </DialogFooter>
          </div>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
