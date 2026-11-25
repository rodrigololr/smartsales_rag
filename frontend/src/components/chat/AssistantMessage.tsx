"use client";

import { BookOpen, Bot, CloudOff, Loader2, RefreshCw, ShieldAlert, Zap, type LucideIcon } from "lucide-react";
import type {
  ChatMessage,
  FeedbackRating,
  FeedbackReasonCategory,
  StreamErrorCode,
} from "@/types/chat";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { CitationList } from "@/components/chat/CitationList";
import { MessageFeedbackBar } from "@/components/chat/MessageFeedbackBar";
import { canReferenceServerMessage } from "@/hooks/use-chat-session";
import { ProductRecommendationCarousel } from "@/components/shop/ProductRecommendationCarousel";
import { cn } from "@/lib/utils";

type FallbackTone = "info" | "warning" | "error";

/** Users see a plain title per code, never the raw code; only real failures offer a retry. */
const FALLBACK_BY_CODE: Record<
  StreamErrorCode,
  { title: string; tone: FallbackTone; icon: LucideIcon; retryable: boolean }
> = {
  // Expected safe answer (R01): the manual simply does not say it.
  LOW_SIMILARITY_FALLBACK: { title: "Informação não encontrada no manual", tone: "info", icon: BookOpen, retryable: false },
  GUARDRAIL_BLOCKED: { title: "Pergunta fora do escopo do consultor", tone: "warning", icon: ShieldAlert, retryable: false },
  LLM_UNAVAILABLE: { title: "Consultor indisponível no momento", tone: "error", icon: CloudOff, retryable: true },
  INTERNAL_ERROR: { title: "Não foi possível concluir a resposta", tone: "error", icon: CloudOff, retryable: true },
};

/** "Title. message" for a fallback turn, as screen readers should hear it. */
export const fallbackAnnouncement = (message: ChatMessage): string =>
  `${FALLBACK_BY_CODE[message.errorCode ?? "INTERNAL_ERROR"].title}. ${message.errorFallback ?? ""}`;

const toneClass: Record<FallbackTone, string> = {
  info: "border-primary/25 bg-primary/5 *:[svg]:text-primary *:data-[slot=alert-description]:text-foreground",
  warning: "border-warning/40 bg-warning/10 *:[svg]:text-warning *:data-[slot=alert-description]:text-foreground",
  error: "",
};

export interface AssistantMessageProps {
  message: ChatMessage;
  sessionId: string;
  onRetry: (messageId: string) => void;
  onFeedback: (
    messageId: string,
    rating: FeedbackRating,
    reason?: FeedbackReasonCategory
  ) => Promise<void>;
}

export function AssistantMessage({
  message,
  sessionId,
  onRetry,
  onFeedback,
}: AssistantMessageProps) {
  const isThinking =
    message.isStreaming && !message.content && !message.errorFallback;

  return (
    <div className="space-y-2" data-testid={`assistant-message-${message.id}`}>
      <div className="flex flex-wrap items-center gap-1.5 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
        <span className="flex items-center gap-1">
          <Bot aria-hidden className="size-3.5 text-primary" />
          Consultor IA
        </span>
        {message.cacheHit ? (
          <Badge variant="outline" className="h-4 gap-0.5 px-1 text-[10px]">
            <Zap className="size-2.5" />
            Cache
          </Badge>
        ) : null}
        {typeof message.ttftMs === "number" ? (
          <span className="normal-case tabular-nums">TTFT {message.ttftMs} ms</span>
        ) : null}
        {message.wasCorrected ? (
          <Badge variant="outline" className="h-4 px-1 text-[10px]">
            Resposta corrigida
          </Badge>
        ) : null}
      </div>

      {isThinking ? (
        <div className="space-y-2 rounded-xl border border-border bg-muted/40 p-3">
          <p className="flex items-center gap-2 text-xs text-muted-foreground">
            <Loader2 className="size-3.5 animate-spin text-primary" />
            Consultando manuais oficiais e estoque...
          </p>
          <Skeleton className="h-3 w-full" />
          <Skeleton className="h-3 w-4/5" />
          <Skeleton className="h-3 w-2/3" />
        </div>
      ) : null}

      {message.errorFallback ? <FallbackAlert message={message} onRetry={onRetry} /> : null}

      {message.content ? (
        <div
          data-testid="assistant-text"
          className="whitespace-pre-wrap rounded-xl rounded-tl-sm border border-border bg-card p-3 text-sm leading-relaxed text-foreground"
        >
          {message.content}
          {message.isStreaming ? (
            <span aria-hidden="true" className="ml-0.5 inline-block h-3.5 w-1 animate-pulse rounded-full bg-primary align-middle" />
          ) : null}
        </div>
      ) : null}

      {message.citations.length ? <CitationList citations={message.citations} /> : null}

      {message.recommendations.length ? (
        <ProductRecommendationCarousel
          products={message.recommendations}
          sessionId={sessionId}
          messageId={canReferenceServerMessage(message) ? (message.serverMessageId ?? message.id) : null}
        />
      ) : null}

      {!message.isStreaming &&
      !message.errorFallback &&
      message.content &&
      canReferenceServerMessage(message) ? (
        <MessageFeedbackBar
          message={message}
          onSubmit={(rating, reason) => onFeedback(message.id, rating, reason)}
        />
      ) : null}
    </div>
  );
}

function FallbackAlert({ message, onRetry }: Pick<AssistantMessageProps, "message" | "onRetry">) {
  const { title, tone, icon: Icon, retryable } = FALLBACK_BY_CODE[message.errorCode ?? "INTERNAL_ERROR"];
  return (
    <Alert
      variant={tone === "error" ? "destructive" : "default"}
      // The finished answer is announced once by ProductAssistant's live region.
      role={undefined}
      data-tone={tone}
      data-testid={`assistant-fallback-${message.id}`}
      className={cn(toneClass[tone], tone === "error" && "border-destructive/30")}
    >
      <Icon aria-hidden />
      <AlertTitle>{title}</AlertTitle>
      <AlertDescription>{message.errorFallback}</AlertDescription>
      {retryable ? (
        <div className="col-start-2 mt-2">
          <Button
            type="button"
            variant="outline"
            size="xs"
            onClick={() => onRetry(message.id)}
            className="gap-1.5"
          >
            <RefreshCw />
            Tentar novamente
          </Button>
        </div>
      ) : null}
    </Alert>
  );
}
