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

/** pt-BR decimal ("4,8"; "1.284"). */
export const formatNumber = (value: number, maximumFractionDigits = 1): string =>
  value.toLocaleString("pt-BR", { maximumFractionDigits });

/** Suffix of a `specs_json` key → unit shown next to the value. */
const SPEC_UNITS: Record<string, string> = {
  c: "°C",
  bar: "bar",
  hz: "Hz",
  min: "min",
  s: "s",
  w: "W",
  v: "V",
  l: "L",
  ml: "ml",
  kg: "kg",
  g: "g",
  cm: "cm",
  mm: "mm",
};

/** Words of `specs_json` keys written without accents in the data. */
const SPEC_WORDS: Record<string, string> = {
  min: "mín.",
  max: "máx.",
  frequencia: "frequência",
  pressao: "pressão",
  potencia: "potência",
  tensao: "tensão",
  agua: "água",
  nivel: "nível",
  rotacao: "rotação",
  dimensoes: "dimensões",
};

/**
 * `specs_json` → [label, value] rows for the technical sheet. Only scalar values from
 * the data are shown (R01: nothing inferred); the unit comes from the key's suffix.
 */
export function specsJsonRows(specs: Record<string, unknown> | undefined): [string, string][] {
  return Object.entries(specs ?? {}).flatMap(([key, raw]): [string, string][] => {
    if (raw === null || typeof raw === "object" || raw === "") return [];
    const words = key.toLowerCase().split("_").filter(Boolean);
    const unit = words.length > 1 ? SPEC_UNITS[words[words.length - 1]] : undefined;
    if (unit) words.pop();
    const label = words.map((word) => SPEC_WORDS[word] ?? word).join(" ");
    const value =
      typeof raw === "number"
        ? formatNumber(raw, 2)
        : typeof raw === "boolean"
          ? raw ? "Sim" : "Não"
          : String(raw);
    return [[label.charAt(0).toUpperCase() + label.slice(1), unit ? `${value} ${unit}` : value]];
  });
}

export const formatMs = (value: number): string => `${formatNumber(Math.round(value), 0)} ms`;

export const formatPercent = (value: number): string =>
  `${(value * 100).toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%`;
