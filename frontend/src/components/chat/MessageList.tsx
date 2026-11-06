"use client";

import React, { useEffect, useRef } from "react";
import { ChatMessage } from "@/types/chat";
import { AssistantMessageBubble } from "./AssistantMessageBubble";
import { User } from "lucide-react";

export interface MessageListProps {
  messages: ChatMessage[];
  isStreaming: boolean;
}

export const MessageList: React.FC<MessageListProps> = ({
  messages,
}) => {
  const bottomRef = useRef<HTMLDivElement>(null);

  // Auto-scroll inteligente durante o streaming (EAP 4.9)
  useEffect(() => {
    if (typeof bottomRef.current?.scrollIntoView === "function") {
      bottomRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages]);

  return (
    <div
      data-testid="message-list"
      className="flex-1 overflow-y-auto p-4 space-y-4"
    >
      {messages.map((message) => {
        if (message.role === "user") {
          return (
            <div
              key={message.id}
              data-testid={`user-message-${message.id}`}
              className="flex items-start justify-end gap-2.5 text-sm"
            >
              <div className="max-w-[85%] p-3.5 rounded-2xl rounded-tr-sm bg-blue-600 text-white leading-relaxed shadow-2xs whitespace-pre-wrap">
                {message.content}
              </div>
              <div className="w-8 h-8 rounded-full bg-slate-200 text-slate-700 flex items-center justify-center flex-shrink-0 mt-0.5">
                <User className="w-4 h-4" />
              </div>
            </div>
          );
        }

        return <AssistantMessageBubble key={message.id} message={message} />;
      })}
      <div ref={bottomRef} />
    </div>
  );
};
