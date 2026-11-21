import Link from "next/link";
import { ArrowLeft, SearchX } from "lucide-react";
import { StoreHeader } from "@/components/layout/StoreHeader";
import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export default function NotFound() {
  return (
    <div className="flex min-h-screen flex-col bg-background">
      <StoreHeader contained />
      <main id="conteudo" className="flex flex-1 items-center justify-center px-4 py-12">
        <div className="flex max-w-md flex-col items-center gap-3 text-center">
          <div className="flex size-12 items-center justify-center rounded-full bg-muted text-muted-foreground">
            <SearchX aria-hidden className="size-6" />
          </div>
          <h1 className="text-xl font-semibold text-foreground">Página não encontrada</h1>
          <p className="text-sm text-muted-foreground">
            O produto ou endereço que você procurou não está no catálogo ativo. Confira o link ou
            escolha um item na vitrine.
          </p>
          <Link href="/" className={cn(buttonVariants(), "mt-2 gap-1.5")}>
            <ArrowLeft />
            Voltar ao catálogo
          </Link>
        </div>
      </main>
    </div>
  );
}
