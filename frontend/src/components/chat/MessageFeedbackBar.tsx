"use client";

import { useState } from "react";
import { Check, ThumbsDown, ThumbsUp } from "lucide-react";
import type {
  ChatMessage,
  FeedbackRating,
  FeedbackReasonCategory,
} from "@/types/chat";
import { feedbackReasons } from "@/lib/mock-data";
import { Button } from "@/components/ui/button";

export interface MessageFeedbackBarProps {
  message: ChatMessage;
  onSubmit: (
    rating: FeedbackRating,
    reason?: FeedbackReasonCategory
  ) => Promise<void>;
}

export function MessageFeedbackBar({
  message,
  onSubmit,
}: MessageFeedbackBarProps) {
  const [showReasons, setShowReasons] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const alreadyRated = Boolean(message.feedback);

  const submit = async (
    rating: FeedbackRating,
    reason?: FeedbackReasonCategory
  ) => {
    setPending(true);
    setError(null);
    try {
      await onSubmit(rating, reason);
      setShowReasons(false);
    } catch {
      setError("Não foi possível registrar seu feedback. Tente novamente.");
    } finally {
      setPending(false);
    }
  };

  if (alreadyRated) {
    return (
      <p
        className="flex items-center gap-1.5 text-xs text-emerald-600"
        data-testid={`feedback-confirmation-${message.id}`}
      >
        <Check className="size-3.5" />
        Obrigado pelo feedback!
      </p>
    );
  }

  return (
    <div className="space-y-2" data-testid={`feedback-bar-${message.id}`}>
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="text-xs text-muted-foreground">Esta resposta foi útil?</span>
        <Button
          type="button"
          variant="ghost"
          size="xs"
          disabled={pending}
          onClick={() => void submit("LIKE")}
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
          onClick={() => setShowReasons((value) => !value)}
          data-testid={`feedback-dislike-${message.id}`}
          className="text-rose-700 hover:bg-rose-50 hover:text-rose-800"
        >
          <ThumbsDown />
          Não útil
        </Button>
      </div>

      {showReasons ? (
        <div className="flex flex-wrap gap-1.5">
          {feedbackReasons.map((reason) => (
            <Button
              key={reason.value}
              type="button"
              variant="outline"
              size="xs"
              disabled={pending}
              onClick={() => void submit("DISLIKE", reason.value)}
              data-testid={`feedback-reason-${reason.value}`}
              className="font-normal"
            >
              {reason.label}
            </Button>
          ))}
        </div>
      ) : null}

      {error ? <p className="text-xs text-rose-600">{error}</p> : null}
    </div>
  );
}
