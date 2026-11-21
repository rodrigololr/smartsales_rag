"use client";

import "./globals.css";
import { cn } from "@/lib/utils";
import { inter } from "@/lib/fonts";
import StoreError from "./error";

/** Replaces the root layout when it fails, so it must render its own document. */
export default function GlobalError({ error, retry }: { error: unknown; retry: () => void }) {
  return (
    <html lang="pt-BR" className={cn("font-sans", inter.variable)}>
      <body className="min-h-screen antialiased">
        <title>Erro — SmartSales RAG</title>
        <StoreError error={error} retry={retry} />
      </body>
    </html>
  );
}
