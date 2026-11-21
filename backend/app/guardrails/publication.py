"""Fail-closed publication checks for a single SKU and its retrieved manual pages.

SQL owns price and electrical/capacity facts. Other technical prose is published
as a verified literal extract; a matching number alone is never textual support.
"""

import re
import unicodedata
from collections.abc import Sequence
from uuid import UUID

from app.guardrails.output import Claim, pt_br_number, technical_claims
from app.models.schemas import CatalogProduct, ProductRecommendation, RetrievedChunk

CITATION_MARK = re.compile(r"\[Fonte:\s*(.+?),\s*p\.\s*(\d+)\]")
_SKU = re.compile(r"\b[A-Z0-9]+(?:-[A-Z0-9]+)+\b", re.IGNORECASE)
_CRITICAL_UNITS = {"V", "W", "L", "BRL"}
_COURTESIES = {"bom uso", "obrigado", "obrigada", "de nada", "posso ajudar com outra duvida"}
_IS = r"(?: e(?: de)?| de)?"  # "é", "é de", "de" or nothing ("A potência é de 1500 W")
_SQL_STATEMENTS = tuple(re.compile(pattern) for pattern in (
    rf"(?:custa|(?:o )?preco(?: atual)?{_IS}) (?:r )?number(?: reais)?",
    r"(?:(?:opera|funciona) em|e) number (?:v|volts?)",
    rf"(?:a )?(?:voltagem|tensao){_IS} number (?:v|volts?)",
    rf"(?:a )?potencia{_IS} number (?:w|watts?|kw|quilowatts?)",
    r"(?:tem|possui)(?: potencia de)? number (?:w|watts?|kw|quilowatts?)(?: de potencia)?",
    rf"(?:a )?capacidade{_IS} number (?:l|litros?|ml|mililitros?)",
    r"(?:tem|possui)(?: capacidade de| cesto de)? number (?:l|litros?|ml|mililitros?)(?: de capacidade)?",
    r"(?:e |(?:a )?voltagem(?: e)? )?bivolt",
))
_QUALIFIERS = {"nao", "apenas", "somente", "exceto", "desde", "proibido", "proibida"}
# A prefix extract must not cut a range or condition off its figure ("2 kg a 3 kg").
_CONTINUATIONS = re.compile(r"(?:a|ate|ou|exceto|quando|(?:no|em) modo)(?: |$)")
_NUMERAL = re.compile(r"\d+(?:[.,]\d+)*")
_PRICE_WORDS = re.compile(r"\b(?:pre[cç]o|custa|custo|valor|reais)\b|R\$", re.IGNORECASE)


def normalized_words(text: str) -> str:
    folded = unicodedata.normalize("NFKD", text.casefold())
    folded = "".join(char for char in folded if not unicodedata.combining(char))
    return " ".join(re.findall(r"\w+", folded))


def _body(chunk: RetrievedChunk) -> str:
    return re.sub(r"^\[PRODUTO:[^\n]*\]\s*", "", chunk.content)


def _numbers(text: str) -> list[str]:
    return [pt_br_number(numeral) for numeral in _NUMERAL.findall(text)]


def _literal_support(sentence: str, chunk: RetrievedChunk) -> bool:
    wanted = normalized_words(sentence)
    figures = _numbers(sentence)
    for fragment in re.split(r"(?<=[.!?])\s+|\n", _body(chunk)):
        evidence = normalized_words(fragment)
        # Word folding drops separators ("1,500 kg" == "1.500 kg"): compare values too.
        if not wanted or _numbers(fragment)[:len(figures)] != figures:
            continue
        if wanted == evidence:
            return True
        # Numeric extracts may omit a trailing noun ("1,2 kg de batatas"), but
        # must retain the subject/predicate, restrictive qualifiers and ranges.
        if technical_claims(sentence) and evidence.startswith(wanted + " "):
            remainder = evidence[len(wanted) + 1:]
            if not (set(remainder.split()) & _QUALIFIERS or _NUMERAL.search(remainder)
                    or _CONTINUATIONS.match(remainder)):
                return True
    return False


class SentenceVerifier:
    def __init__(self, product: CatalogProduct | ProductRecommendation, chunks: Sequence[RetrievedChunk]) -> None:
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
        if normalized_words(plain) in _COURTESIES:
            return sentence
        for chunk in self._chunks:
            if _literal_support(plain, chunk):
                self.cited_chunk_ids.add(chunk.chunk_id)
                return self._with_citation(sentence, chunk)
        return sentence if self._sql_statement(plain, claims) else None

    def _sql_statement(self, sentence: str, claims: set[Claim]) -> bool:
        if not claims or not claims <= self._sql_claims:
            return False
        structure = normalized_words(re.sub(r"\d+(?:[.,]\d+)*", " number ", sentence))
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


class ConsultativeVerifier:
    """Each explicitly named SQL recommendation has an isolated fact verifier.

    No manual evidence is borrowed between products. Multi-product compound
    claims are refused; one SKU and one verified attribute per sentence.
    """

    def __init__(
        self, product: CatalogProduct, chunks: Sequence[RetrievedChunk],
        recommendations: Sequence[ProductRecommendation],
    ) -> None:
        self._base = SentenceVerifier(product, chunks)
        self._options = {card.sku: SentenceVerifier(card, []) for card in recommendations
                         if card.sku != product.sku}
        self._options[product.sku] = self._base

    @property
    def cited_chunk_ids(self) -> set[UUID]:
        return self._base.cited_chunk_ids

    def approve(self, sentence: str) -> str | None:
        anchored = re.fullmatch(
            r"(\s*(?:-\s+)?)SKU ([A-Za-z0-9_-]+):\s*(.+)", sentence, re.DOTALL | re.IGNORECASE
        )
        if anchored is None:
            return self._base.approve(sentence)
        bullet, raw_sku, statement = anchored.groups()
        sku = raw_sku.upper()
        verifier = self._options.get(sku)
        if verifier is None:
            return None
        approved = verifier.approve(statement)
        return f"{bullet}SKU {sku}: {approved}" if approved is not None else None
