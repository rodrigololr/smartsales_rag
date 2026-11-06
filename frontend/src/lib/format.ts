import type { MarketplaceType, VoltageType } from "@/types/chat";

export const formatBRL = (value: number) =>
  new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
  }).format(value);

export const marketplaceLabel = (marketplace: MarketplaceType): string =>
  ({
    AMAZON: "Amazon",
    MERCADO_LIVRE: "Mercado Livre",
    SHOPEE: "Shopee",
    LOJA_OFICIAL: "Loja Oficial",
  })[marketplace];

export const voltageBadgeClass = (voltage: VoltageType): string => {
  if (voltage === "220V") return "border-amber-200 bg-amber-100 text-amber-800";
  if (voltage === "127V") return "border-sky-200 bg-sky-100 text-sky-800";
  if (voltage === "BIVOLT") return "border-emerald-200 bg-emerald-100 text-emerald-800";
  return "border-border bg-muted text-muted-foreground";
};

export const createId = (): string => {
  if (typeof globalThis.crypto?.randomUUID === "function") {
    return globalThis.crypto.randomUUID();
  }
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (char) => {
    const random = (Math.random() * 16) | 0;
    const value = char === "x" ? random : (random & 0x3) | 0x8;
    return value.toString(16);
  });
};

export const formatDateTime = (iso: string): string =>
  new Intl.DateTimeFormat("pt-BR", {
    dateStyle: "short",
    timeStyle: "short",
  }).format(new Date(iso));

export const formatMs = (value: number): string => `${Math.round(value)} ms`;

export const formatPercent = (value: number): string =>
  `${(value * 100).toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%`;
