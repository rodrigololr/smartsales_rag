"use client";

import React, { useState } from "react";
import { Product } from "@/types/catalog";
import { X, Send, Bot, Sparkles, BookOpen, AlertCircle } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetTitle,
} from "@/components/ui/sheet";

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

  if (!product) {
    return null;
  }

  const quickSuggestions = [
    `Qual é a voltagem oficial deste modelo (${product.voltage})?`,
    product.capacity_liters
      ? `A capacidade de ${product.capacity_liters}L atende quantas pessoas?`
      : "Quais acessórios são compatíveis com este produto?",
    "Quais materiais de forma e assadeira posso utilizar?",
  ];

  const handleSend = (e: React.FormEvent) => {
    e.preventDefault();
    if (!prompt.trim()) return;
    // Disparo inicial do chat (implementado no pacote F02 com useSSEChatStream)
    setPrompt("");
  };

  const handleSuggestionClick = (suggestion: string) => {
    setPrompt(suggestion);
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
              <SheetDescription className="max-w-[260px] truncate text-xs">
                Ancorado no manual de: {product.name}
              </SheetDescription>
            </div>
          </div>

          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            data-testid="close-drawer-btn"
            onClick={onClose}
            aria-label="Fechar painel"
          >
            <X className="size-5" />
          </Button>
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

        {/* Corpo da Conversa / Sugestões */}
        <div className="flex-1 space-y-4 overflow-y-auto p-4">
          <div className="flex items-start gap-2.5 rounded-xl bg-muted p-3.5 text-xs leading-relaxed text-muted-foreground">
            <Sparkles className="mt-0.5 size-4 shrink-0 text-primary" />
            <div>
              <p className="mb-1 font-medium text-foreground">
                Olá! Sou o consultor técnico de vendas.
              </p>
              <p>
                Posso esclarecer especificações exatas deste produto, validar voltagem,
                medidas e sugerir upgrades compatíveis com base nos manuais de fábrica.
              </p>
            </div>
          </div>

          <div>
            <h4 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Perguntas frequentes deste produto
            </h4>
            <div className="flex flex-col gap-2">
              {quickSuggestions.map((suggestion, idx) => (
                <Button
                  key={idx}
                  type="button"
                  variant="outline"
                  onClick={() => handleSuggestionClick(suggestion)}
                  className="group h-auto w-full justify-between gap-2 whitespace-normal px-2.5 py-2 text-left text-xs font-normal text-muted-foreground hover:text-foreground"
                >
                  <span>{suggestion}</span>
                  <Sparkles className="shrink-0 text-muted-foreground/60 group-hover:text-primary" />
                </Button>
              ))}
            </div>
          </div>
        </div>

        {/* Área de Input */}
        <form onSubmit={handleSend} className="border-t border-border bg-card p-4">
          <div className="relative flex items-center">
            <Input
              type="text"
              data-testid="chat-prompt-input"
              aria-label="Pergunta para o consultor"
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder={`Tire uma dúvida sobre ${product.name}...`}
              className="pr-12"
            />
            <Button
              type="submit"
              size="icon-sm"
              disabled={!prompt.trim()}
              className="absolute right-1.5"
              aria-label="Enviar pergunta"
            >
              <Send className="size-4" />
            </Button>
          </div>
          <p className="mt-2 flex items-center justify-center gap-1 text-center text-[10px] text-muted-foreground">
            <AlertCircle className="size-3" /> Respostas ancoradas estritamente em manuais de
            fábrica.
          </p>
        </form>
      </SheetContent>
    </Sheet>
  );
};
