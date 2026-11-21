"use client";

import { useState } from "react";
import { Check, RefreshCw, ThumbsDown, ThumbsUp } from "lucide-react";
import type {
  ChatMessage,
  FeedbackRating,
  FeedbackReasonCategory,
} from "@/types/chat";
import { feedbackReasons } from "@/lib/mock-data";
import { ChatApiError } from "@/lib/chat-api";
import { Button } from "@/components/ui/button";

export interface MessageFeedbackBarProps {
  message: ChatMessage;
  onSubmit: (
    rating: FeedbackRating,
    reason?: FeedbackReasonCategory
  ) => Promise<void>;
}

interface FeedbackAttempt {
  rating: FeedbackRating;
  reason?: FeedbackReasonCategory;
}

const GENERIC_FEEDBACK_ERROR =
  "O serviço de avaliações está indisponível agora. Sua escolha foi mantida; tente enviar de novo.";

const FEEDBACK_ERROR_BY_STATUS: Record<number, string> = {
  404: "Não encontramos esta resposta no servidor para registrar a avaliação.",
  410: "Sua sessão expirou. Recarregue a página e faça a pergunta de novo para avaliar.",
  422: "A avaliação não pôde ser validada pelo servidor. Tente enviar de novo.",
  429: "Muitas avaliações em pouco tempo. Aguarde alguns segundos e tente de novo.",
};

export const describeFeedbackError = (error: unknown): string =>
  (error instanceof ChatApiError && FEEDBACK_ERROR_BY_STATUS[error.status]) ||
  GENERIC_FEEDBACK_ERROR;

export function MessageFeedbackBar({
  message,
  onSubmit,
}: MessageFeedbackBarProps) {
  const [showReasons, setShowReasons] = useState(false);
  const [pending, setPending] = useState(false);
  const [failedAttempt, setFailedAttempt] = useState<FeedbackAttempt | null>(null);
  const [error, setError] = useState<string | null>(null);

  const submit = async (attempt: FeedbackAttempt) => {
    setPending(true);
    setError(null);
    try {
      await onSubmit(attempt.rating, attempt.reason);
      setShowReasons(false);
      setFailedAttempt(null);
    } catch (submitError) {
      console.warn("feedback_submit_failed", submitError);
      setFailedAttempt(attempt);
      setError(describeFeedbackError(submitError));
    } finally {
      setPending(false);
    }
  };

  if (message.feedbackAlreadyRecorded) {
    return (
      <p
        className="flex items-center gap-1.5 text-xs text-muted-foreground"
        data-testid={`feedback-confirmation-${message.id}`}
      >
        <Check className="size-3.5" />
        Esta resposta já foi avaliada.
      </p>
    );
  }

  if (message.feedback) {
    return (
      <p
        className="flex items-center gap-1.5 text-xs text-emerald-700"
        data-testid={`feedback-confirmation-${message.id}`}
      >
        <Check className="size-3.5" />
        Obrigado pelo feedback!
      </p>
    );
  }

  return (
    <div className="space-y-2" data-testid={`feedback-bar-${message.id}`} aria-busy={pending}>
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="text-xs text-muted-foreground">Esta resposta foi útil?</span>
        <Button
          type="button"
          variant="ghost"
          size="xs"
          disabled={pending}
          onClick={() => void submit({ rating: "LIKE" })}
          data-testid={`feedback-like-${message.id}`}
          className="text-emerald-700 hover:bg-emerald-50 hover:text-emerald-800"
        >
          <ThumbsUp />
          Útil
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="xs"
          disabled={pending}
          aria-expanded={showReasons}
          onClick={() => setShowReasons((value) => !value)}
          data-testid={`feedback-dislike-${message.id}`}
          className="text-rose-700 hover:bg-rose-50 hover:text-rose-800"
        >
          <ThumbsDown />
          Não útil
        </Button>
      </div>

      {showReasons ? (
        <div className="flex flex-wrap gap-1.5" role="group" aria-label="Motivo da avaliação negativa">
          {feedbackReasons.map((reason) => (
            <Button
              key={reason.value}
              type="button"
              variant="outline"
              size="xs"
              disabled={pending}
              aria-pressed={failedAttempt?.reason === reason.value}
              onClick={() => void submit({ rating: "DISLIKE", reason: reason.value })}
              data-testid={`feedback-reason-${reason.value}`}
              className="font-normal aria-pressed:border-rose-300 aria-pressed:bg-rose-50"
            >
              {reason.label}
            </Button>
          ))}
        </div>
      ) : null}

      {error && failedAttempt ? (
        <div role="alert" className="flex flex-wrap items-center gap-2 text-xs text-rose-700">
          <span>{error}</span>
          <Button
            type="button"
            variant="outline"
            size="xs"
            disabled={pending}
            onClick={() => void submit(failedAttempt)}
            data-testid={`feedback-retry-${message.id}`}
            className="gap-1"
          >
            <RefreshCw />
            Tentar enviar de novo
          </Button>
        </div>
      ) : null}
    </div>
  );
}
