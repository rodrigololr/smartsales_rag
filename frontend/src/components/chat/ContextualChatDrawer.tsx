"use client";

import type { Product } from "@/types/catalog";
import type { ChatSession } from "@/hooks/use-chat-session";
import { Sheet, SheetContent, SheetDescription, SheetTitle } from "@/components/ui/sheet";
import { ProductAssistant } from "@/components/chat/ProductAssistant";

export interface ContextualChatDrawerProps {
  product: Product;
  chat: ChatSession;
  isOpen: boolean;
  onClose: () => void;
}

/** Mobile shell of the product assistant; on large screens it is docked in the page. */
export function ContextualChatDrawer({ product, chat, isOpen, onClose }: ContextualChatDrawerProps) {
  return (
    <Sheet open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <SheetContent
        data-testid="contextual-chat-drawer"
        data-sku={product.sku}
        side="right"
        showCloseButton={false}
        className="w-full gap-0 p-0 data-[side=right]:w-full data-[side=right]:sm:w-[440px]"
      >
        <SheetTitle className="sr-only">Consultor IA</SheetTitle>
        <SheetDescription className="sr-only">Respostas sobre {product.name}</SheetDescription>
        <ProductAssistant product={product} chat={chat} onClose={onClose} />
      </SheetContent>
    </Sheet>
  );
}
