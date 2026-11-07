"use client";

import { Bot, Loader2, RefreshCw, ShieldAlert, Zap } from "lucide-react";
import type {
  ChatMessage,
  FeedbackRating,
  FeedbackReasonCategory,
} from "@/types/chat";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { CitationList } from "@/components/chat/CitationList";
import { MessageFeedbackBar } from "@/components/chat/MessageFeedbackBar";
import { ProductRecommendationCarousel } from "@/components/shop/ProductRecommendationCarousel";

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
      <div className="flex flex-wrap items-center gap-1.5 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
        <span className="flex items-center gap-1">
          <Bot className="size-3.5 text-primary" />
          Consultor IA
        </span>
        {message.cacheHit ? (
          <Badge variant="outline" className="h-4 gap-0.5 px-1 text-[9px]">
            <Zap className="size-2.5" />
            Cache
          </Badge>
        ) : null}
        {typeof message.ttftMs === "number" ? (
          <span className="normal-case">TTFT {message.ttftMs} ms</span>
        ) : null}
        {message.wasCorrected ? (
          <Badge variant="outline" className="h-4 px-1 text-[9px]">
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

      {message.errorFallback ? (
        <Alert variant="destructive" data-testid={`assistant-fallback-${message.id}`}>
          <ShieldAlert />
          <AlertTitle>Resposta bloqueada com segurança</AlertTitle>
          <AlertDescription>
            {message.errorFallback}
            {message.errorCode ? (
              <span className="mt-1 block font-mono text-[10px] opacity-80">
                {message.errorCode}
              </span>
            ) : null}
          </AlertDescription>
          <div className="mt-2">
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
        </Alert>
      ) : null}

      {message.content ? (
        <div className="whitespace-pre-wrap rounded-xl rounded-tl-sm border border-border bg-card p-3 text-sm leading-relaxed text-foreground">
          {message.content}
          {message.isStreaming ? (
            <span className="ml-0.5 inline-block h-3.5 w-1 animate-pulse rounded-full bg-primary align-middle" />
          ) : null}
        </div>
      ) : null}

      {message.citations.length ? <CitationList citations={message.citations} /> : null}

      {message.recommendations.length ? (
        <ProductRecommendationCarousel
          products={message.recommendations}
          sessionId={sessionId}
          messageId={message.id}
        />
      ) : null}

      {!message.isStreaming && !message.errorFallback && message.content ? (
        <MessageFeedbackBar
          message={message}
          onSubmit={(rating, reason) => onFeedback(message.id, rating, reason)}
        />
      ) : null}
    </div>
  );
}
