import { describe, expect, it } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { CitationList } from "@/components/chat/CitationList";
import { citationsForProduct, findProduct } from "@/lib/mock-data";
import type { ManualCitation } from "@/types/chat";

const airfryerCitations = (): ManualCitation[] => {
  const product = findProduct("AF-400-220V");
  if (!product) throw new Error("Produto base ausente no mock");
  return citationsForProduct(product);
};

describe("UT-F03-01: acordeão de citações do manual técnico", () => {
  it("expande e recolhe o trecho literal com documento, página e seção", () => {
    const citations = airfryerCitations();
    const citation = citations[0];
    render(<CitationList citations={citations} />);

    const toggle = screen.getByTestId(`citation-badge-${citation.chunk_id}`);
    const panel = screen.getByTestId(`citation-panel-${citation.chunk_id}`);
    expect(toggle).toHaveTextContent(`${citation.manual_title} — p. ${citation.page_number}`);
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(toggle).toHaveAttribute("aria-controls", panel.id);
    expect(panel).not.toBeVisible();

    fireEvent.click(toggle);

    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(panel).toBeVisible();
    expect(panel).toHaveTextContent(/Formas de alumínio com diâmetro de até 20 cm/);
    if (citation.section_title) expect(panel).toHaveTextContent(citation.section_title);

    fireEvent.click(toggle);

    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(panel).not.toBeVisible();
  });

  it("omite a seção quando o chunk não tem section_title", () => {
    const [citation] = airfryerCitations();
    const withoutSection: ManualCitation = { ...citation, section_title: undefined };
    render(<CitationList citations={[withoutSection]} />);

    fireEvent.click(screen.getByTestId(`citation-badge-${citation.chunk_id}`));

    expect(screen.queryByTestId(`citation-section-${citation.chunk_id}`)).not.toBeInTheDocument();
    expect(screen.getByTestId(`citation-panel-${citation.chunk_id}`)).toHaveTextContent(
      citation.excerpt
    );
  });

  it("não renderiza nada sem citações", () => {
    const { container } = render(<CitationList citations={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renderiza citação da base de conhecimento (sku = KB-*) sem assumir produto", () => {
    const kbCitation: ManualCitation = {
      chunk_id: "kb-twitch-1",
      sku: "KB-TWITCH-TRANSMISSAO",
      manual_title: "Twitch qualidade de transmissão",
      page_number: 1,
      similarity_score: 1.0,
      excerpt: "Altura máxima de vídeo recomendada: 1080 px.",
    };
    render(<CitationList citations={[kbCitation]} />);

    const toggle = screen.getByTestId("citation-badge-kb-twitch-1");
    expect(toggle).toHaveTextContent("Twitch qualidade de transmissão — p. 1");
    fireEvent.click(toggle);
    expect(screen.getByTestId("citation-panel-kb-twitch-1")).toHaveTextContent(
      "Altura máxima de vídeo recomendada: 1080 px."
    );
  });
});
