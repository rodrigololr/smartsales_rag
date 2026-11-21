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
});
