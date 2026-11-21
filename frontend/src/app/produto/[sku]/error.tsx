"use client";

import { RouteErrorState } from "@/components/shared/RouteErrorState";

export default function ProductError({ error, retry }: { error: unknown; retry: () => void }) {
  return (
    <RouteErrorState
      error={error}
      retry={retry}
      title="Não conseguimos carregar este produto"
      description="Os dados de preço e estoque não responderam agora. Tente de novo em instantes ou escolha outro item no catálogo."
    />
  );
}
