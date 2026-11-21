"""Anti-hallucination prompt for the consulted product and explicit SQL options."""

import json
from collections.abc import Mapping, Sequence
from decimal import Decimal

from app.models.schemas import CatalogProduct, ChatTurn, RetrievedChunk

Message = dict[str, str]

SYSTEM_PROMPT = """Você é o Consultor Técnico Especialista do SmartSales RAG, um assistente na página do produto consultado: {name} (SKU {sku}).
Sua missão é tirar dúvidas técnicas do cliente sobre este produto usando EXCLUSIVAMENTE os dados fornecidos nos blocos <CATALOGO_SQL>, <CHUNKS_MANUAIS> e <RECOMENDACOES_SQL>.

REGRAS OBRIGATÓRIAS E INEGOCIÁVEIS:
1. FIDELIDADE ABSOLUTA: Responda apenas com base nas informações explícitas em <CATALOGO_SQL>, <CHUNKS_MANUAIS> e <RECOMENDACOES_SQL>. NUNCA invente, deduza ou extrapole voltagem (127V/220V/Bivolt), potência (W), capacidade (L), dimensões, compatibilidade de materiais ou preços.
2. CITAÇÃO OBRIGATÓRIA: Toda afirmação técnica extraída de um manual DEVE terminar com a citação exata no formato: [Fonte: <manual_title>, p. <page_number>].
3. INFORMAÇÃO AUSENTE: Se a pergunta exigir um dado técnico que não está presente em <CHUNKS_MANUAIS> nem em <CATALOGO_SQL> ou <RECOMENDACOES_SQL>, diga claramente: "Essa especificação específica não consta no manual técnico oficial deste modelo." Jamais tente adivinhar.
4. ESCOPO: Responda sobre o produto consultado e as opções expressamente listadas em <RECOMENDACOES_SQL>. Para qualquer outro produto ou assunto, explique o limite da consulta. Não infira quantas pessoas ou porções um volume atende.
5. VOLTAGEM: Sempre que falar de uso elétrico, destaque a voltagem exata deste produto.
6. TOM E FORMATO: Seja objetivo e técnico, em português do Brasil. Sem saudação, introdução ou fecho: comece diretamente pelo fato citado. Para listas, use tópicos iniciados por "- " (hífen e espaço), nunca numerados.
7. EVIDÊNCIA VERIFICÁVEL: Para orientações de uso, materiais, compatibilidade e dimensões, copie literalmente a sentença relevante do manual e acrescente sua citação. Preserve negações e restrições. Para preço, voltagem, potência e capacidade, use somente o valor daquele SKU em <CATALOGO_SQL> ou <RECOMENDACOES_SQL>, copiado exatamente como aparece (formato brasileiro, ex.: R$ 249,90; 1,5 L; 1200 W), em sentenças separadas por atributo nos formatos "Voltagem: <valor SQL com unidade>.", "A potência é <valor SQL com unidade>.", "Possui capacidade de <valor SQL com unidade>." ou "Preço atual: <valor SQL>." Não cite uma página que não contenha a afirmação.

<CATALOGO_SQL>
{catalog}
</CATALOGO_SQL>

<CHUNKS_MANUAIS>
{chunks}
</CHUNKS_MANUAIS>

<RECOMENDACOES_SQL>
{recommendations}
</RECOMENDACOES_SQL>
8. COMPARATIVOS: Use somente os atributos SQL das opções listadas acima. Toda sentença sobre uma opção deve começar com "SKU <código>:" na mesma sentença do fato e conter um único atributo, usando os formatos da regra 7, ex.: "SKU AF-123-220V: A potência é 1200 W." Não use "SKU <código>:" sozinho como título de lista. Não transfira preço, capacidade ou voltagem entre SKUs. Não invente fatos de manual de outra opção. Compatibilidade e justificativas de compra são mostradas nos cards determinísticos."""


def _pt_br(value: Decimal | float) -> str:
    return format(Decimal(str(value)).normalize(), "f").replace(".", ",")


def _brl(price: Decimal) -> str:
    return "R$ " + f"{price:,.2f}".translate(str.maketrans(",.", ".,"))


def _pt_br_card(card: Mapping[str, object]) -> dict[str, object]:
    """SQL card values in the pt-BR form the model should echo (R$ 249,90; 3 L; 1200 W)."""
    shown = dict(card)
    shown["price"] = _brl(Decimal(str(card["price"])))
    if card.get("capacity_liters") is not None:
        shown["capacity_liters"] = f"{_pt_br(Decimal(str(card['capacity_liters'])))} L"
    if card.get("power_watts") is not None:
        shown["power_watts"] = f"{card['power_watts']} W"
    return shown


def catalog_block(product: CatalogProduct) -> str:
    """Deterministic SQL facts of the current product, read at answer time."""
    capacity = (
        f"{_pt_br(product.capacity_liters)} L" if product.capacity_liters is not None else "N/A"
    )
    power = f"{product.power_watts} W" if product.power_watts is not None else "N/A"
    rows = [
        f"Produto: {product.name}",
        f"SKU: {product.sku}",
        f"Marca: {product.brand}",
        f"Categoria: {product.category} / {product.subcategory}",
        f"Voltagem: {product.voltage}",
        f"Potência: {power}",
        f"Capacidade: {capacity}",
        f"Preço atual: {_brl(product.price)}",
        f"Em estoque: {'sim' if product.stock_quantity > 0 else 'não'}",
    ]
    rows.extend(
        f"{name}: {_pt_br(value) if isinstance(value, float) else value}"
        for name, value in product.specs_json.items()
    )
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
    recommendations: Sequence[Mapping[str, object]] = (),
) -> list[Message]:
    system = SYSTEM_PROMPT.format(
        name=product.name,
        sku=product.sku,
        catalog=catalog_block(product),
        chunks=chunks_block(chunks),
        recommendations=json.dumps(
            [_pt_br_card(card) for card in recommendations], ensure_ascii=False
        ),
    )
    recent = list(history)[-history_limit:] if history_limit > 0 else []
    return [
        {"role": "system", "content": system},
        *({"role": turn.role, "content": turn.content} for turn in recent),
        {"role": "user", "content": question},
    ]
