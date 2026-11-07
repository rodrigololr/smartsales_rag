import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MessageFeedbackBar } from "@/components/chat/MessageFeedbackBar";
import type { ChatMessage } from "@/types/chat";

const message: ChatMessage = {
  id: "message-1",
  role: "assistant",
  content: "A Airfryer opera em 220V.",
  isStreaming: false,
  citations: [],
  recommendations: [],
  feedback: null,
  errorFallback: null,
  errorCode: null,
};

describe("UT-F03-02: MessageFeedbackBar", () => {
  it("envia DISLIKE com WRONG_VOLTAGE e confirma o registro", async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    const { rerender } = render(
      <MessageFeedbackBar message={message} onSubmit={onSubmit} />
    );

    fireEvent.click(screen.getByTestId("feedback-dislike-message-1"));
    fireEvent.click(screen.getByTestId("feedback-reason-WRONG_VOLTAGE"));

    await waitFor(() =>
      expect(onSubmit).toHaveBeenCalledWith("DISLIKE", "WRONG_VOLTAGE")
    );

    rerender(
      <MessageFeedbackBar
        message={{ ...message, feedback: "DISLIKE", feedbackReason: "WRONG_VOLTAGE" }}
        onSubmit={onSubmit}
      />
    );

    expect(screen.getByTestId("feedback-confirmation-message-1")).toHaveTextContent(
      /Obrigado pelo feedback/i
    );
  });
});
