import { describe, expect, it } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { CitationList } from "@/components/chat/CitationList";
import { citationsForProduct, findProduct } from "@/lib/mock-data";

describe("UT-F03-01: CitationBadge e trecho literal do manual", () => {
  it("abre o trecho original ao clicar no badge da página", () => {
    const product = findProduct("AF-400-220V");
    if (!product) throw new Error("Produto base ausente no mock");
    const citations = citationsForProduct(product);
    const citation = citations[0];

    render(<CitationList citations={citations} />);

    fireEvent.click(screen.getByTestId(`citation-badge-${citation.chunk_id}`));

    expect(screen.getByTestId("citation-dialog")).toBeInTheDocument();
    expect(screen.getByText(citation.manual_title)).toBeInTheDocument();
    expect(screen.getByText(/Formas de alumínio com diâmetro de até 20 cm/)).toBeInTheDocument();
    expect(screen.getByText(/Página 14/)).toBeInTheDocument();
  });
});
