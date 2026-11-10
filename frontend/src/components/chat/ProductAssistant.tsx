"use client";

import { useEffect, useRef, useState } from "react";
import { AlertCircle, BookOpen, Bot, RotateCcw, Send, Sparkles, X } from "lucide-react";
import type { Product } from "@/types/catalog";
import type { ChatSession } from "@/hooks/use-chat-session";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { AssistantMessage } from "@/components/chat/AssistantMessage";
import { cn } from "@/lib/utils";

export function suggestionsFor(product: Product): string[] {
  const voltage = `Qual é a voltagem oficial deste modelo (${product.voltage})?`;
  if (product.subcategory === "Cafeteiras") {
    return [voltage, "Qual é a pressão da bomba?", "Como faço a descalcificação?"];
  }
  if (product.capacity_liters) {
    return [
      voltage,
      `A capacidade de ${product.capacity_liters}L atende quantas pessoas?`,
      "Quais materiais de forma e assadeira posso utilizar?",
    ];
  }
  return [voltage, "Como devo fazer a limpeza?", "Quais são os cuidados de uso?"];
}

export interface ProductAssistantProps {
  product: Product;
  chat: ChatSession;
  /** Shown only where the assistant can be dismissed (mobile sheet). */
  onClose?: () => void;
  className?: string;
}

/** Product-scoped consultant: docked on the product page, or inside the mobile sheet. */
export function ProductAssistant({ product, chat, onClose, className }: ProductAssistantProps) {
  const { sessionId, messages, isStreaming, send, retry, reset, submitFeedback } = chat;
  const [prompt, setPrompt] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const element = scrollRef.current;
    if (!element) return;
    if (typeof element.scrollTo === "function") {
      element.scrollTo({ top: element.scrollHeight, behavior: "smooth" });
    } else {
      element.scrollTop = element.scrollHeight;
    }
  }, [messages]);

  const handleSend = (text: string) => {
    if (!text.trim() || isStreaming) return;
    send(text);
    setPrompt("");
  };

  return (
    <div
      data-testid="product-assistant"
      data-sku={product.sku}
      className={cn("flex h-full min-h-0 flex-col bg-card", className)}
    >
      <div className="flex items-center justify-between border-b border-border bg-muted/50 p-4">
        <div className="flex min-w-0 items-center gap-3">
          <div className="flex size-9 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground shadow-sm">
            <Bot className="size-5" />
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-1.5">
              <h2 className="text-sm font-semibold text-foreground">Consultor IA</h2>
              <Badge variant="secondary" className="text-[10px] font-bold uppercase tracking-wider">
                RAG
              </Badge>
            </div>
            <p className="truncate text-xs text-muted-foreground">
              Respostas sobre {product.name}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-1">
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            onClick={() => {
              reset();
              setPrompt("");
            }}
            data-testid="reset-chat-btn"
            aria-label="Reiniciar conversa"
            className="text-muted-foreground"
          >
            <RotateCcw className="size-4" />
          </Button>
          {onClose ? (
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              data-testid="close-drawer-btn"
              onClick={onClose}
              aria-label="Fechar consultor"
              className="text-muted-foreground"
            >
              <X className="size-5" />
            </Button>
          ) : null}
        </div>
      </div>

      <div className="flex items-center justify-between gap-3 border-b border-border bg-primary/5 px-4 py-2.5 text-xs">
        <div className="flex min-w-0 items-center gap-2 text-foreground">
          <BookOpen className="size-4 shrink-0 text-primary" />
          <span className="truncate">
            Manual e ficha técnica de <strong>{product.sku}</strong>
          </span>
        </div>
        <Badge variant="secondary" className="font-bold text-primary">
          {product.voltage}
        </Badge>
      </div>

      <div ref={scrollRef} aria-live="polite" className="flex-1 space-y-4 overflow-y-auto p-4">
        {messages.length === 0 ? (
          <>
            <div className="flex items-start gap-2.5 rounded-xl bg-muted p-3.5 text-xs leading-relaxed text-muted-foreground">
              <Sparkles className="mt-0.5 size-4 shrink-0 text-primary" />
              <div>
                <p className="mb-1 font-medium text-foreground">Olá! Tire suas dúvidas sobre este produto.</p>
                <p>
                  Respondo sobre especificações, uso e cuidados com base no manual oficial e na
                  ficha técnica, sempre citando a página da fonte.
                </p>
              </div>
            </div>

            <div>
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Perguntas frequentes deste produto
              </h3>
              <div className="flex flex-wrap gap-2">
                {suggestionsFor(product).map((suggestion, index) => (
                  <Button
                    key={suggestion}
                    type="button"
                    variant="secondary"
                    disabled={isStreaming}
                    onClick={() => handleSend(suggestion)}
                    data-testid={`quick-suggestion-${index}`}
                    className="h-auto whitespace-normal rounded-full bg-primary/10 px-3 py-1.5 text-left text-xs font-medium text-primary hover:bg-primary/15"
                  >
                    {suggestion}
                  </Button>
                ))}
              </div>
            </div>
          </>
        ) : (
          messages.map((message) =>
            message.role === "user" ? (
              <div key={message.id} className="flex justify-end">
                <div className="max-w-[85%] rounded-xl rounded-tr-sm bg-primary px-3 py-2 text-sm leading-relaxed text-primary-foreground">
                  {message.content}
                </div>
              </div>
            ) : (
              <AssistantMessage
                key={message.id}
                message={message}
                sessionId={sessionId}
                onRetry={retry}
                onFeedback={submitFeedback}
              />
            )
          )
        )}
      </div>

      <form
        onSubmit={(event) => {
          event.preventDefault();
          handleSend(prompt);
        }}
        className="border-t border-border bg-card p-4"
      >
        <div className="relative flex items-center">
          <Input
            type="text"
            data-testid="chat-prompt-input"
            aria-label="Pergunta para o consultor"
            value={prompt}
            onChange={(event) => setPrompt(event.target.value)}
            disabled={isStreaming}
            placeholder="Faça uma pergunta sobre este produto"
            className="pr-12"
          />
          <Button
            type="submit"
            size="icon-sm"
            disabled={!prompt.trim() || isStreaming}
            className="absolute right-1.5"
            aria-label="Enviar pergunta"
          >
            <Send className="size-4" />
          </Button>
        </div>
        <p className="mt-2 flex items-center justify-center gap-1 text-center text-[10px] text-muted-foreground">
          <AlertCircle className="size-3" /> Respostas ancoradas no manual oficial do fabricante.
        </p>
      </form>
    </div>
  );
}
