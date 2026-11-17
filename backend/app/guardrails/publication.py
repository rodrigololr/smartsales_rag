"""Fail-closed publication checks for a single SKU and its retrieved manual pages.

SQL owns price and electrical/capacity facts. Other technical prose is published
as a verified literal extract; a matching number alone is never textual support.
"""

import re
import unicodedata
from collections.abc import Sequence
from uuid import UUID

from app.guardrails.output import Claim, technical_claims
from app.models.schemas import CatalogProduct, RetrievedChunk

CITATION_MARK = re.compile(r"\[Fonte:\s*(.+?),\s*p\.\s*(\d+)\]")
_SKU = re.compile(r"\b[A-Z0-9]+(?:-[A-Z0-9]+)+\b", re.IGNORECASE)
_CRITICAL_UNITS = {"V", "W", "L", "BRL"}
_COURTESIES = {"bom uso", "obrigado", "obrigada", "de nada", "posso ajudar com outra duvida"}
_SQL_STATEMENTS = tuple(re.compile(pattern) for pattern in (
    r"(?:custa|(?:o )?preco(?: atual)?(?: e| de)?) (?:r )?number(?: reais)?",
    r"(?:opera|funciona) em number (?:v|volts?)",
    r"(?:a )?(?:voltagem|tensao)(?: e| de)? number (?:v|volts?)",
    r"(?:a )?potencia(?: e| de)? number (?:w|watts?|kw|quilowatts?)",
    r"(?:tem|possui)(?: potencia de)? number (?:w|watts?|kw|quilowatts?)(?: de potencia)?",
    r"(?:a )?capacidade(?: e| de)? number (?:l|litros?|ml|mililitros?)",
    r"(?:tem|possui)(?: capacidade de| cesto de)? number (?:l|litros?|ml|mililitros?)(?: de capacidade)?",
    r"(?:e |(?:a )?voltagem(?: e)? )?bivolt",
))
_QUALIFIERS = {"nao", "apenas", "somente", "exceto", "desde", "proibido", "proibida"}
_PRICE_WORDS = re.compile(r"\b(?:pre[cç]o|custa|custo|valor|reais)\b|R\$", re.IGNORECASE)


def _normalized(text: str) -> str:
    folded = unicodedata.normalize("NFKD", text.casefold())
    folded = "".join(char for char in folded if not unicodedata.combining(char))
    return " ".join(re.findall(r"\w+", folded))


def _body(chunk: RetrievedChunk) -> str:
    return re.sub(r"^\[PRODUTO:[^\n]*\]\s*", "", chunk.content)


def _literal_support(sentence: str, chunk: RetrievedChunk) -> bool:
    wanted = _normalized(sentence)
    for fragment in re.split(r"(?<=[.!?])\s+|\n", _body(chunk)):
        evidence = _normalized(fragment)
        if wanted and wanted == evidence:
            return True
        # Numeric extracts may omit a trailing noun ("1,2 kg de batatas"), but
        # must retain the subject/predicate and all restrictive qualifiers.
        if technical_claims(sentence) and evidence.startswith(wanted + " "):
            remainder = set(evidence[len(wanted):].split())
            if not remainder & _QUALIFIERS:
                return True
    return False


class SentenceVerifier:
    def __init__(self, product: CatalogProduct, chunks: Sequence[RetrievedChunk]) -> None:
        self._product = product
        self._chunks = [chunk for chunk in chunks if chunk.sku == product.sku]
        self.cited_chunk_ids: set[UUID] = set()
        self._sql_claims: set[Claim] = {(format(product.price.normalize(), "f"), "BRL")}
        if product.voltage == "BIVOLT":
            self._sql_claims.update({("bivolt", "V"), ("127", "V"), ("220", "V")})
        elif product.voltage in {"127V", "220V"}:
            self._sql_claims.add((product.voltage[:-1], "V"))
        if product.power_watts is not None:
            self._sql_claims.add((str(product.power_watts), "W"))
        if product.capacity_liters is not None:
            self._sql_claims.add((format(product.capacity_liters.normalize(), "f"), "L"))

    def approve(self, sentence: str) -> str | None:
        marks = {(title.strip(), int(page)) for title, page in CITATION_MARK.findall(sentence)}
        plain = CITATION_MARK.sub("", sentence).strip().rstrip(".!? ")
        if "[Fonte:" in plain:
            return None  # malformed citation must not slip through as ordinary prose
        if any(any(char.isdigit() for char in sku) and sku != self._product.sku
               for sku in _SKU.findall(plain)):
            return None
        claims = technical_claims(plain)
        if _PRICE_WORDS.search(plain) and any(char.isdigit() for char in plain):
            if not any(unit == "BRL" for _, unit in claims):
                return None  # unrecognized currency syntax cannot fall back to stale manual prose
        if {claim for claim in claims if claim[1] in _CRITICAL_UNITS} - self._sql_claims:
            return None
        if marks:
            return sentence if self._cited_support(plain, marks) else None
        if _normalized(plain) in _COURTESIES:
            return sentence
        for chunk in self._chunks:
            if _literal_support(plain, chunk):
                self.cited_chunk_ids.add(chunk.chunk_id)
                return self._with_citation(sentence, chunk)
        return sentence if self._sql_statement(plain, claims) else None

    def _sql_statement(self, sentence: str, claims: set[Claim]) -> bool:
        if not claims or not claims <= self._sql_claims:
            return False
        structure = _normalized(re.sub(r"\d+(?:[.,]\d+)*", " number ", sentence))
        structure = re.sub(
            r"^(?:(?:este|esse|esta|essa|o|a) (?:modelo|produto)|ele|ela) ", "", structure,
        )
        # Bind the attribute to its unit; a vocabulary/number set alone accepts
        # "voltagem 1500 W" when 1500 W exists as the product's *power*.
        return any(pattern.fullmatch(structure) for pattern in _SQL_STATEMENTS)

    def _cited_support(self, plain: str, marks: set[tuple[str, int]]) -> bool:
        supporting_ids: set[UUID] = set()
        for title, page in marks:
            candidates = [chunk for chunk in self._chunks
                          if (chunk.manual_title, chunk.page_number) == (title, page)]
            supporting = next((chunk for chunk in candidates if _literal_support(plain, chunk)), None)
            if supporting is None:
                return False
            supporting_ids.add(supporting.chunk_id)
        self.cited_chunk_ids.update(supporting_ids)
        return True

    @staticmethod
    def _with_citation(sentence: str, chunk: RetrievedChunk) -> str:
        trailing = sentence[len(sentence.rstrip()):]
        plain = sentence.strip().rstrip(".!? ")
        return f"{plain} [Fonte: {chunk.manual_title}, p. {chunk.page_number}].{trailing}"
