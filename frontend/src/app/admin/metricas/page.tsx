import type { Metadata } from "next";
import { AdminMetricsDashboard } from "@/components/admin/AdminMetricsDashboard";

export const metadata: Metadata = {
  title: "Métricas do Operador — SmartSales RAG",
  description:
    "Painel de qualidade e conversão do consultor IA: TTFT, cache, feedback e checkouts.",
};

export default function AdminMetricsPage() {
  return <AdminMetricsDashboard />;
}
