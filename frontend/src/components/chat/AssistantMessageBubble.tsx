"use client";

import React from "react";
import { ChatMessage } from "@/types/chat";
import { Bot, Sparkles, ShieldCheck, AlertTriangle, Zap } from "lucide-react";

export interface AssistantMessageBubbleProps {
  message: ChatMessage;
}

export const AssistantMessageBubble: React.FC<AssistantMessageBubbleProps> = ({
  message,
}) => {
  const isConnecting = message.isStreaming && !message.content && !message.errorFallback;

  return (
    <div
      data-testid={`assistant-message-${message.id}`}
      className="flex items-start gap-3 text-sm text-slate-800"
    >
      <div className="w-8 h-8 rounded-full bg-blue-600 text-white flex items-center justify-center flex-shrink-0 shadow-xs mt-0.5">
        <Bot className="w-4 h-4" />
      </div>

      <div className="flex-1 space-y-2 max-w-[90%]">
        {/* Estado CONNECTING: Skeleton pulsante (EAP 3.4 / 4.9) */}
        {isConnecting && (
          <div
            data-testid="streaming-skeleton"
            className="p-3.5 rounded-2xl bg-blue-50/70 border border-blue-100 flex items-center gap-3 animate-pulse text-xs text-blue-700 font-medium"
          >
            <Sparkles className="w-4 h-4 text-blue-600 animate-spin" />
            <span>Consultando manuais oficiais e estoque...</span>
          </div>
        )}

        {/* Mensagem de Erro ou Fallback Seguro */}
        {message.errorFallback && (
          <div
            data-testid="fallback-message-box"
            className="p-3.5 rounded-2xl bg-amber-50 border border-amber-200 text-xs text-amber-900 leading-relaxed flex items-start gap-2.5"
          >
            <AlertTriangle className="w-4 h-4 text-amber-600 flex-shrink-0 mt-0.5" />
            <div>
              <p className="font-semibold mb-0.5">Aviso de Conformidade Técnica</p>
              <p>{message.errorFallback}</p>
            </div>
          </div>
        )}

        {/* Conteúdo Normal ou Corrigido */}
        {message.content && (
          <div className="p-3.5 rounded-2xl rounded-tl-sm bg-slate-100 text-slate-900 leading-relaxed shadow-2xs whitespace-pre-wrap">
            {message.content}
            {message.isStreaming && (
              <span className="inline-block w-1.5 h-4 ml-1 bg-blue-600 animate-pulse align-middle" />
            )}
          </div>
        )}

        {/* Selo de Correção Atômica por Guardrail (UT-F02-02) */}
        {message.wasCorrected && (
          <div
            data-testid="correction-badge"
            className="flex items-center gap-1.5 text-[11px] font-semibold text-emerald-700 bg-emerald-50 px-2.5 py-1 rounded-md border border-emerald-200 w-fit"
          >
            <ShieldCheck className="w-3.5 h-3.5 text-emerald-600" />
            <span>Resposta validada pelo Guardrail Anti-Alucinação</span>
          </div>
        )}

        {/* Metadados Técnicos de Telemetria (TTFT / Cache) */}
        {(message.ttftMs !== undefined || message.cacheHit) && !message.isStreaming && (
          <div className="flex items-center gap-2 text-[10px] text-slate-400 font-mono">
            {message.cacheHit && (
              <span className="flex items-center gap-1 text-emerald-600">
                <Zap className="w-3 h-3" /> Cache Semântico Hit
              </span>
            )}
            {message.ttftMs !== undefined && (
              <span>TTFT: {message.ttftMs}ms</span>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
