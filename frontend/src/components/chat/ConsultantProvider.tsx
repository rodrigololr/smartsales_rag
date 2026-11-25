"use client";

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { createChatStore, useChatSession, type ChatStore } from "@/hooks/use-chat-session";

type StoreBySku = Map<string | null, ChatStore>;
const ConsultantContext = createContext<StoreBySku | null>(null);

export function ConsultantProvider({ children }: { children: ReactNode }) {
  const [stores] = useState<StoreBySku>(() => new Map());

  useEffect(() => () => {
    for (const store of stores.values()) store.controller?.abort();
  }, [stores]);

  return <ConsultantContext.Provider value={stores}>{children}</ConsultantContext.Provider>;
}

export function useConsultant(sku: string | null = null) {
  const stores = useContext(ConsultantContext);
  // Allocate a conversation only when its page is visited. Null is the catalogue chat.
  let store = stores?.get(sku);
  if (stores && !store) {
    store = createChatStore(sku);
    stores.set(sku, store);
  }
  return { chat: useChatSession(store) };
}
