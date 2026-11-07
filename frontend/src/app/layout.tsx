import "./globals.css";
import type { Metadata } from "next";
import React from "react";
import { Inter } from "next/font/google";
import { cn } from "@/lib/utils";

const inter = Inter({subsets:['latin'],variable:'--font-sans'});

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
        {children}
      </body>
    </html>
  );
}
