import "./globals.css";
import type { Metadata } from "next";
import React from "react";
import { inter } from "@/lib/fonts";
import { cn } from "@/lib/utils";

export const metadata: Metadata = {
  title: "SmartSales RAG — Consultor Especialista de Vendas",
  description: "Assistente consultivo de vendas B2B/B2B2C com busca híbrida e citações em manuais técnicos.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="pt-BR" className={cn("font-sans", inter.variable)}>
      <body className="min-h-screen antialiased">
        <a
          href="#conteudo"
          className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50 focus:rounded-md focus:bg-primary focus:px-3 focus:py-2 focus:text-sm focus:font-medium focus:text-primary-foreground"
        >
          Pular para o conteúdo
        </a>
        {children}
      </body>
    </html>
  );
}
