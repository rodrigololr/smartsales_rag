"use client";

import { useEffect, useRef, useState } from "react";
import {
  AlertCircle,
  BookOpen,
  Bot,
  RotateCcw,
  Send,
  Sparkles,
  X,
} from "lucide-react";
import type { Product } from "@/types/catalog";
import { useChatSession } from "@/hooks/use-chat-session";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetTitle,
} from "@/components/ui/sheet";
import { AssistantMessage } from "@/components/chat/AssistantMessage";

export interface ContextualChatDrawerProps {
  product: Product | null;
  isOpen: boolean;
  onClose: () => void;
}

export const ContextualChatDrawer: React.FC<ContextualChatDrawerProps> = ({
  product,
  isOpen,
  onClose,
}) => {
  const [prompt, setPrompt] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);
  const {
    sessionId,
    messages,
    isStreaming,
    send,
    retry,
    reset,
    submitFeedback,
  } = useChatSession(product);

  useEffect(() => {
    const element = scrollRef.current;
    if (!element) return;
    if (typeof element.scrollTo === "function") {
      element.scrollTo({ top: element.scrollHeight, behavior: "smooth" });
    } else {
      element.scrollTop = element.scrollHeight;
    }
  }, [messages, isOpen]);

  if (!product) return null;

  const quickSuggestions = [
    `Qual é a voltagem oficial deste modelo (${product.voltage})?`,
    product.capacity_liters
      ? `A capacidade de ${product.capacity_liters}L atende quantas pessoas?`
      : "Quais acessórios são compatíveis com este produto?",
    "Quais materiais de forma e assadeira posso utilizar?",
  ];

  const handleSend = (text: string) => {
    if (!text.trim() || isStreaming) return;
    send(text);
    setPrompt("");
  };

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    handleSend(prompt);
  };

  const handleReset = () => {
    reset();
    setPrompt("");
  };

  return (
    <Sheet
      open={isOpen}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <SheetContent
        data-testid="contextual-chat-drawer"
        data-sku={product.sku}
        side="right"
        showCloseButton={false}
        className="w-full gap-0 p-0 data-[side=right]:w-full data-[side=right]:sm:w-[480px]"
        aria-label="Painel do Consultor IA"
      >
        {/* Cabeçalho do Drawer */}
        <div className="flex items-center justify-between border-b border-border bg-muted/50 p-4">
          <div className="flex min-w-0 items-center gap-3">
            <div className="flex size-9 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground shadow-sm">
              <Bot className="size-5" />
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-1.5">
                <SheetTitle className="text-sm font-semibold">Consultor Especialista</SheetTitle>
                <Badge variant="secondary" className="text-[10px] font-bold uppercase tracking-wider">
                  IA RAG
                </Badge>
              </div>
              <SheetDescription className="max-w-[240px] truncate text-xs">
                Ancorado no manual de: {product.name}
              </SheetDescription>
            </div>
          </div>

          <div className="flex items-center gap-1">
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              onClick={handleReset}
              data-testid="reset-chat-btn"
              aria-label="Reiniciar conversa"
              className="text-muted-foreground"
            >
              <RotateCcw className="size-4" />
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              data-testid="close-drawer-btn"
              onClick={onClose}
              aria-label="Fechar painel"
              className="text-muted-foreground"
            >
              <X className="size-5" />
            </Button>
          </div>
        </div>

        {/* Cartão de Contexto do Produto Ativo */}
        <div className="flex items-center justify-between gap-3 border-b border-border bg-primary/5 px-4 py-3 text-xs">
          <div className="flex items-center gap-2 text-foreground">
            <BookOpen className="size-4 shrink-0 text-primary" />
            <span className="truncate">
              Manual técnico de <strong>{product.sku}</strong> ativo
            </span>
          </div>
          <Badge variant="secondary" className="font-bold text-primary">
            {product.voltage}
          </Badge>
        </div>

        {/* Corpo da Conversa */}
        <div ref={scrollRef} className="flex-1 space-y-4 overflow-y-auto p-4">
          {messages.length === 0 ? (
            <>
              <div className="flex items-start gap-2.5 rounded-xl bg-muted p-3.5 text-xs leading-relaxed text-muted-foreground">
                <Sparkles className="mt-0.5 size-4 shrink-0 text-primary" />
                <div>
                  <p className="mb-1 font-medium text-foreground">
                    Olá! Sou o consultor técnico de vendas.
                  </p>
                  <p>
                    Posso esclarecer especificações exatas deste produto, validar
                    voltagem, medidas e sugerir upgrades compatíveis com base nos
                    manuais de fábrica.
                  </p>
                </div>
              </div>

              <div>
                <h4 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  Perguntas frequentes deste produto
                </h4>
                <div className="flex flex-col gap-2">
                  {quickSuggestions.map((suggestion, index) => (
                    <Button
                      key={suggestion}
                      type="button"
                      variant="outline"
                      disabled={isStreaming}
                      onClick={() => handleSend(suggestion)}
                      data-testid={`quick-suggestion-${index}`}
                      className="group h-auto w-full justify-between gap-2 whitespace-normal px-2.5 py-2 text-left text-xs font-normal text-muted-foreground hover:text-foreground"
                    >
                      <span>{suggestion}</span>
                      <Sparkles className="shrink-0 text-muted-foreground/60 group-hover:text-primary" />
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

        {/* Área de Input */}
        <form onSubmit={handleSubmit} className="border-t border-border bg-card p-4">
          <div className="relative flex items-center">
            <Input
              type="text"
              data-testid="chat-prompt-input"
              aria-label="Pergunta para o consultor"
              value={prompt}
              onChange={(event) => setPrompt(event.target.value)}
              disabled={isStreaming}
              placeholder={`Tire uma dúvida sobre ${product.name}...`}
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
            <AlertCircle className="size-3" /> Respostas ancoradas estritamente em
            manuais de fábrica.
          </p>
        </form>
      </SheetContent>
    </Sheet>
  );
};
