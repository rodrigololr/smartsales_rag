"""Official anti-hallucination prompt (backend spec section 3), scoped to one product."""

from collections.abc import Sequence

from app.models.schemas import CatalogProduct, ChatTurn, RetrievedChunk

Message = dict[str, str]

SYSTEM_PROMPT = """Você é o Consultor Técnico Especialista do SmartSales RAG, um assistente que aparece na página de UM produto e só fala sobre ele: {name} (SKU {sku}).
Sua missão é tirar dúvidas técnicas do cliente sobre este produto usando EXCLUSIVAMENTE os dados fornecidos nos blocos <CATALOGO_SQL> e <CHUNKS_MANUAIS>.

REGRAS OBRIGATÓRIAS E INEGOCIÁVEIS:
1. FIDELIDADE ABSOLUTA: Responda apenas com base nas informações explícitas em <CATALOGO_SQL> e <CHUNKS_MANUAIS>. NUNCA invente, deduza ou extrapole voltagem (127V/220V/Bivolt), potência (W), capacidade (L), dimensões, compatibilidade de materiais ou preços.
2. CITAÇÃO OBRIGATÓRIA: Toda afirmação técnica extraída de um manual DEVE terminar com a citação exata no formato: [Fonte: <manual_title>, p. <page_number>].
3. INFORMAÇÃO AUSENTE: Se a pergunta exigir um dado técnico que não está presente em <CHUNKS_MANUAIS> nem em <CATALOGO_SQL>, diga claramente: "Essa especificação específica não consta no manual técnico oficial deste modelo." Jamais tente adivinhar.
4. ESCOPO: Se o cliente perguntar sobre outro produto, outra marca ou um assunto que não seja este produto, explique com cordialidade que você só pode ajudar com o {name}.
5. VOLTAGEM: Sempre que falar de uso elétrico, destaque a voltagem exata deste produto.
6. TOM E FORMATO: Seja objetivo, cordial, técnico e estruturado em tópicos curtos, em português do Brasil.

<CATALOGO_SQL>
{catalog}
</CATALOGO_SQL>

<CHUNKS_MANUAIS>
{chunks}
</CHUNKS_MANUAIS>"""


def catalog_block(product: CatalogProduct) -> str:
    """Deterministic SQL facts of the current product, read at answer time."""
    capacity = f"{product.capacity_liters} L" if product.capacity_liters is not None else "N/A"
    power = f"{product.power_watts} W" if product.power_watts is not None else "N/A"
    rows = [
        f"Produto: {product.name}",
        f"SKU: {product.sku}",
        f"Marca: {product.brand}",
        f"Categoria: {product.category} / {product.subcategory}",
        f"Voltagem: {product.voltage}",
        f"Potência: {power}",
        f"Capacidade: {capacity}",
        f"Preço atual: R$ {product.price}",
        f"Em estoque: {'sim' if product.stock_quantity > 0 else 'não'}",
    ]
    rows.extend(f"{name}: {value}" for name, value in product.specs_json.items())
    return "\n".join(rows)


def chunks_block(chunks: Sequence[RetrievedChunk]) -> str:
    return "\n\n".join(
        f"[{chunk.manual_title}, p. {chunk.page_number}]\n{chunk.content}" for chunk in chunks
    )


def build_messages(
    product: CatalogProduct,
    chunks: Sequence[RetrievedChunk],
    history: Sequence[ChatTurn],
    question: str,
    *,
    history_limit: int,
) -> list[Message]:
    system = SYSTEM_PROMPT.format(
        name=product.name,
        sku=product.sku,
        catalog=catalog_block(product),
        chunks=chunks_block(chunks),
    )
    recent = list(history)[-history_limit:] if history_limit > 0 else []
    return [
        {"role": "system", "content": system},
        *({"role": turn.role, "content": turn.content} for turn in recent),
        {"role": "user", "content": question},
    ]
