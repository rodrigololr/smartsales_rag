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

/** Products without mains power (USB, battery, cosmetics) come as "N/A" from the catalog. */
export const hasVoltage = (voltage: VoltageType): boolean => voltage !== "N/A";
export const voltageLabel = (voltage: VoltageType): string =>
  voltage === "BIVOLT" ? "Bivolt" : hasVoltage(voltage) ? voltage : "Não se aplica";

export const voltageBadgeClass = (voltage: VoltageType): string => {
  if (voltage === "220V") return "border-amber-200 bg-amber-100 text-amber-800 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200";
  if (voltage === "127V") return "border-sky-200 bg-sky-100 text-sky-800 dark:border-sky-800 dark:bg-sky-950 dark:text-sky-200";
  if (voltage === "BIVOLT") return "border-emerald-200 bg-emerald-100 text-emerald-800 dark:border-emerald-800 dark:bg-emerald-950 dark:text-emerald-200";
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
  horas: "h",
  dias: "dias",
  meses: "meses",
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
  removivel: "removível",
  lavavel: "lavável",
  automatico: "automático",
  automatica: "automática",
  eletrico: "elétrico",
  eletrica: "elétrica",
  valvula: "válvula",
  seguranca: "segurança",
  funcao: "função",
  funcoes: "funções",
  numero: "número",
  maximo: "máximo",
  minimo: "mínimo",
  ceramica: "cerâmica",
  area: "área",
  util: "útil",
  camara: "câmara",
  acessorios: "acessórios",
  programacao: "programação",
  protecao: "proteção",
  energetica: "energética",
  liquido: "líquido",
  rapido: "rápido",
  conexao: "conexão",
  iluminacao: "iluminação",
  botoes: "botões",
  navegacao: "navegação",
  resolucao: "resolução",
  xicaras: "xícaras",
  giratoria: "giratória",
  ions: "íons",
  resistencia: "resistência",
  ruido: "ruído",
  dpi: "DPI",
  fps: "FPS",
  led: "LED",
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

/** Only http(s) links from the gateway become hrefs (blocks javascript:, data:, ...). */
export const safeHttpUrl = (url: string | null | undefined): string | null => {
  if (!url) return null;
  try {
    const { protocol } = new URL(url);
    return protocol === "http:" || protocol === "https:" ? url : null;
  } catch {
    return null;
  }
};
