"use client";

import React, { useState } from "react";
import { Product } from "@/types/catalog";
import { useSSEChatStream } from "@/hooks/useSSEChatStream";
import { MessageList } from "./MessageList";
import { ResetSessionButton } from "./ResetSessionButton";
import { X, Send, Bot, Sparkles, BookOpen, AlertCircle } from "lucide-react";

export interface ContextualChatDrawerProps {
  product: Product | null;
  isOpen: boolean;
  onClose: () => void;
  voltagePreference?: string;
}

export const ContextualChatDrawer: React.FC<ContextualChatDrawerProps> = ({
  product,
  isOpen,
  onClose,
  voltagePreference = "ALL",
}) => {
  const [prompt, setPrompt] = useState("");
  const {
    messages,
    isStreaming,
    errorMessage,
    sendMessage,
    resetSession,
    retryLastMessage,
  } = useSSEChatStream();

  if (!isOpen || !product) {
    return null;
  }

  const quickSuggestions = [
    `Qual é a voltagem oficial deste modelo (${product.voltage})?`,
    product.capacity_liters
      ? `A capacidade de ${product.capacity_liters}L atende quantas pessoas?`
      : "Quais acessórios são compatíveis com este produto?",
    "Quais materiais de forma e assadeira posso utilizar?",
  ];

  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!prompt.trim() || isStreaming) return;
    const currentPrompt = prompt;
    setPrompt("");
    await sendMessage(currentPrompt, {
      skuContext: product.sku,
      voltagePreference: voltagePreference !== "ALL" ? voltagePreference : product.voltage,
    });
  };

  const handleSuggestionClick = async (suggestion: string) => {
    if (isStreaming) return;
    await sendMessage(suggestion, {
      skuContext: product.sku,
      voltagePreference: voltagePreference !== "ALL" ? voltagePreference : product.voltage,
    });
  };

  return (
    <aside
      data-testid="contextual-chat-drawer"
      data-sku={product.sku}
      className="fixed inset-y-0 right-0 w-full sm:w-[500px] bg-white border-l border-slate-200 shadow-2xl flex flex-col z-50 transition-all duration-300"
      aria-label="Painel do Consultor IA"
    >
      {/* Cabeçalho do Drawer */}
      <div className="p-4 border-b border-slate-200 bg-slate-50 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-full bg-blue-600 text-white flex items-center justify-center shadow-xs">
            <Bot className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-1.5">
              <h3 className="font-semibold text-slate-900 text-sm">Consultor Especialista</h3>
              <span className="text-[10px] uppercase font-bold tracking-wider px-1.5 py-0.5 rounded bg-blue-100 text-blue-700">
                IA RAG
              </span>
            </div>
            <p className="text-xs text-slate-500 truncate max-w-[240px]">
              {product.name}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-1">
          <ResetSessionButton onReset={resetSession} disabled={isStreaming} />
          <button
            type="button"
            data-testid="close-drawer-btn"
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-200 transition-colors"
            aria-label="Fechar painel"
          >
            <X className="w-5 h-5" />
          </button>
        </div>
      </div>

      {/* Cartão de Ancoragem de Contexto */}
      <div className="px-4 py-2.5 bg-blue-50/70 border-b border-blue-100 flex items-center justify-between gap-3 text-xs">
        <div className="flex items-center gap-2 text-slate-700">
          <BookOpen className="w-4 h-4 text-blue-600 flex-shrink-0" />
          <span className="truncate">
            Manual de <strong>{product.sku}</strong> ({product.name}) ativo
          </span>
        </div>
        <span className="font-bold text-blue-700 bg-blue-100 px-2 py-0.5 rounded text-[11px]">
          {product.voltage}
        </span>
      </div>

      {/* Área de Conteúdo da Conversa */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {messages.length === 0 ? (
          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            <div className="bg-slate-100 rounded-xl p-3.5 text-xs text-slate-700 leading-relaxed flex items-start gap-2.5">
              <Sparkles className="w-4 h-4 text-blue-600 flex-shrink-0 mt-0.5" />
              <div>
                <p className="font-medium text-slate-900 mb-1">Olá! Sou o consultor técnico de vendas.</p>
                <p>
                  Posso esclarecer especificações exatas deste produto, validar voltagem, medidas e sugerir upgrades compatíveis com base nos manuais de fábrica.
                </p>
              </div>
            </div>

            <div>
              <h4 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">
                Perguntas frequentes deste produto
              </h4>
              <div className="flex flex-col gap-2">
                {quickSuggestions.map((suggestion, idx) => (
                  <button
                    key={idx}
                    type="button"
                    onClick={() => handleSuggestionClick(suggestion)}
                    disabled={isStreaming}
                    className="text-left text-xs p-2.5 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 hover:border-blue-300 text-slate-700 transition-colors flex items-center justify-between group disabled:opacity-50"
                  >
                    <span>{suggestion}</span>
                    <Sparkles className="w-3.5 h-3.5 text-slate-300 group-hover:text-blue-500 flex-shrink-0" />
                  </button>
                ))}
              </div>
            </div>
          </div>
        ) : (
          <MessageList messages={messages} isStreaming={isStreaming} />
        )}
      </div>

      {/* Banner de Erro com Botão de Tentar Novamente */}
      {errorMessage && (
        <div className="px-4 py-2 bg-rose-50 border-t border-rose-200 flex items-center justify-between text-xs text-rose-700">
          <span>{errorMessage}</span>
          <button
            type="button"
            onClick={retryLastMessage}
            className="font-semibold underline hover:text-rose-900"
          >
            Tentar novamente
          </button>
        </div>
      )}

      {/* Formulário de Envio do Prompt */}
      <form onSubmit={handleSend} className="p-4 border-t border-slate-200 bg-white">
        <div className="relative flex items-center">
          <input
            type="text"
            data-testid="chat-prompt-input"
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            disabled={isStreaming}
            placeholder={
              isStreaming
                ? "Aguarde a resposta do assistente..."
                : `Tire uma dúvida sobre ${product.name}...`
            }
            className="w-full text-sm pl-3.5 pr-12 py-2.5 rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all placeholder:text-slate-400 disabled:bg-slate-100 disabled:cursor-not-allowed"
          />
          <button
            type="submit"
            data-testid="send-prompt-btn"
            disabled={!prompt.trim() || isStreaming}
            className="absolute right-1.5 p-1.5 rounded-md bg-blue-600 text-white hover:bg-blue-700 disabled:bg-slate-200 disabled:text-slate-400 disabled:cursor-not-allowed transition-colors"
            aria-label="Enviar pergunta"
          >
            <Send className="w-4 h-4" />
          </button>
        </div>
        <p className="text-[10px] text-slate-400 text-center mt-2 flex items-center justify-center gap-1">
          <AlertCircle className="w-3 h-3" /> Respostas ancoradas estritamente em manuais de fábrica.
        </p>
      </form>
    </aside>
  );
};
