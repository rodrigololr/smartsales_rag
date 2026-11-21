"use client";

import React, { createContext, useContext, useMemo, useState } from "react";
import type { Product } from "@/types/catalog";
import { useChatSession, type ChatSession } from "@/hooks/use-chat-session";

export interface ConsultantContextValue {
  chat: ChatSession;
  contextProduct: Product | null;
  setContextProduct: (product: Product | null) => void;
}

const ConsultantContext = createContext<ConsultantContextValue | null>(null);

export function ConsultantProvider({ children }: { children: React.ReactNode }) {
  const chat = useChatSession();
  const [contextProduct, setContextProduct] = useState<Product | null>(null);
  const value = useMemo(
    () => ({ chat, contextProduct, setContextProduct }),
    [chat, contextProduct]
  );
  return <ConsultantContext.Provider value={value}>{children}</ConsultantContext.Provider>;
}

export function useConsultant(): ConsultantContextValue {
  const context = useContext(ConsultantContext);
  const fallbackChat = useChatSession();
  const [fallbackProduct, setFallbackProduct] = useState<Product | null>(null);
  return useMemo(
    () =>
      context ?? {
        chat: fallbackChat,
        contextProduct: fallbackProduct,
        setContextProduct: setFallbackProduct,
      },
    [context, fallbackChat, fallbackProduct]
  );
}
