"use client";

import { RouteErrorState } from "@/components/shared/RouteErrorState";

export default function StoreError({ error, retry }: { error: unknown; retry: () => void }) {
  return (
    <RouteErrorState
      error={error}
      retry={retry}
      title="Não foi possível abrir esta página"
      description="Algo falhou ao carregar a loja. Tente de novo em instantes; se persistir, volte ao catálogo."
    />
  );
}
