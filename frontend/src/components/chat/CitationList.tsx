"use client";

import { useState } from "react";
import { FileText } from "lucide-react";
import type { ManualCitation } from "@/types/chat";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

export function CitationList({ citations }: { citations: ManualCitation[] }) {
  const [active, setActive] = useState<ManualCitation | null>(null);

  if (!citations.length) return null;

  return (
    <div className="flex flex-wrap gap-1.5" data-testid="citation-list">
      {citations.map((citation) => (
        <Button
          key={citation.chunk_id}
          type="button"
          variant="outline"
          size="xs"
          onClick={() => setActive(citation)}
          data-testid={`citation-badge-${citation.chunk_id}`}
          className="max-w-full justify-start gap-1.5 border-primary/20 bg-primary/5 px-2 py-1 text-left text-[11px] font-medium text-primary hover:bg-primary/10"
        >
          <FileText className="shrink-0" />
          <span className="truncate">
            {citation.manual_title} — p. {citation.page_number}
          </span>
        </Button>
      ))}

      {active ? (
        <Dialog
          open
          onOpenChange={(open) => {
            if (!open) setActive(null);
          }}
        >
          <DialogContent className="sm:max-w-md" data-testid="citation-dialog">
            <DialogHeader>
              <DialogTitle>{active.manual_title}</DialogTitle>
              <DialogDescription>
                Página {active.page_number}
                {active.section_title ? ` · ${active.section_title}` : ""}
              </DialogDescription>
            </DialogHeader>

            <blockquote className="rounded-lg border-l-2 border-primary bg-muted/60 p-3 text-sm leading-relaxed text-foreground italic">
              “{active.excerpt}”
            </blockquote>

            <p className="text-xs text-muted-foreground">
              Trecho literal extraído do manual indexado (chunk{" "}
              <span className="font-mono">{active.chunk_id}</span>, similaridade{" "}
              {(active.similarity_score * 100).toFixed(0)}%).
            </p>

            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setActive(null)}>
                Fechar
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      ) : null}
    </div>
  );
}
