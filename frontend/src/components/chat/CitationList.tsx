"use client";

import { useId, useState } from "react";
import { ChevronDown, FileText } from "lucide-react";
import type { ManualCitation } from "@/types/chat";

/** Accordion of manual sources: each item expands to the literal excerpt (UC01, RF11). */
export function CitationList({ citations }: { citations: ManualCitation[] }) {
  const baseId = useId();
  const [openChunks, setOpenChunks] = useState<ReadonlySet<string>>(() => new Set());

  if (!citations.length) return null;

  const toggle = (chunkId: string) =>
    setOpenChunks((previous) => {
      const next = new Set(previous);
      if (!next.delete(chunkId)) next.add(chunkId);
      return next;
    });

  return (
    <ul
      aria-label="Fontes consultadas no manual"
      className="divide-y divide-primary/10 overflow-hidden rounded-lg border border-primary/20 bg-primary/5"
      data-testid="citation-list"
    >
      {citations.map((citation, index) => {
        const isOpen = openChunks.has(citation.chunk_id);
        const panelId = `${baseId}-citation-${index}`;
        return (
          <li key={citation.chunk_id}>
            <button
              type="button"
              aria-expanded={isOpen}
              aria-controls={panelId}
              onClick={() => toggle(citation.chunk_id)}
              data-testid={`citation-badge-${citation.chunk_id}`}
              className="flex w-full items-center gap-1.5 min-h-9 px-2.5 py-1.5 text-left text-xs font-medium text-primary outline-none hover:bg-primary/10 focus-visible:ring-2 focus-visible:ring-ring/60 focus-visible:ring-inset"
            >
              <FileText className="size-3.5 shrink-0" aria-hidden />
              <span className="min-w-0 flex-1 truncate">
                {citation.manual_title} — p. {citation.page_number}
              </span>
              <ChevronDown
                aria-hidden
                className="size-3.5 shrink-0 transition-transform motion-reduce:transition-none data-[open=true]:rotate-180"
                data-open={isOpen}
              />
            </button>

            <div
              id={panelId}
              role="region"
              aria-label={`${citation.manual_title}, página ${citation.page_number}`}
              hidden={!isOpen}
              data-testid={`citation-panel-${citation.chunk_id}`}
              className="space-y-1.5 bg-background/60 px-2.5 pt-1 pb-2.5"
            >
              {citation.section_title ? (
                <p
                  className="text-[11px] text-muted-foreground"
                  data-testid={`citation-section-${citation.chunk_id}`}
                >
                  Seção: {citation.section_title}
                </p>
              ) : null}
              <blockquote className="border-l-2 border-primary pl-2.5 text-xs leading-relaxed text-foreground">
                “{citation.excerpt}”
              </blockquote>
              <p className="text-[11px] text-muted-foreground">
                Trecho literal do manual, página {citation.page_number} (similaridade{" "}
                {(citation.similarity_score * 100).toFixed(0)}%).
              </p>
            </div>
          </li>
        );
      })}
    </ul>
  );
}
