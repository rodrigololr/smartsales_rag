"""Deterministic safety checks and fail-closed aggregation; cognition is scored by RAGAS."""

import math
import re
import unicodedata
from decimal import Decimal

from app.guardrails.output import Claim, technical_claims
from app.models.schemas import CatalogProduct, ProductRelation
from app.recommendation.engine import CROSS_SELL_MAX_PRICE_RATIO, UPSELL_MAX_PRICE_RATIO

from .models import (
    EvalCaseResult,
    EvaluationReport,
    GateResult,
    GoldenSetFixture,
    ObservedTurn,
    RunIdentity,
)

FAITHFULNESS_FLOOR = 0.85
RELEVANCE_FLOOR = 0.85
RETRIEVAL_FLOOR = 0.80
HALLUCINATION_CEILING = 0.05
TOP_K = 5
CITATION = re.compile(r"\[Fonte:\s*(.+?),\s*p\.\s*(\d+)\]", re.IGNORECASE)
_AMOUNT = r"(\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?|\d+(?:[.,]\d{1,2})?)(?![\d.,])"
PRICE = re.compile(r"(?:R\$\s*|(?:custa|preço(?: atual)?(?: é| de)?)\s+)" + _AMOUNT, re.I)
REALS = re.compile(_AMOUNT + r"\s*reais\b", re.I)
_FIGURE = re.compile(
    r"(?<![\w.,])(\d+(?:[.,]\d+)?)\s*(kW|quilowatts?|W|watts?|mL|mililitros?|L|litros?|V|volts?|kg|g|cm|mm|bar|Hz|°C)\b",
    re.I,
)
_BIVOLT = re.compile(r"\bbivolt\b", re.I)
_SKU = re.compile(r"\b[A-Z]+(?:-[A-Z0-9]+)+\b", re.I)
DENIAL = re.compile(
    r"\b(?:nao|nunca|jamais)\s+(?:(?:e|eh|opera|funciona|suporta|tem|possui|custa|"
    r"aceita|deve|ser|usad[oa]|ligad[oa]|em|a|com|uma|tomada|de)\s+)*$"
    r"|\b(?:proibid[oa]|incompativel)\s+(?:em\s+|com\s+)?$"
)


def normalize(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()


def number(raw: str) -> Decimal:
    return Decimal(
        raw.replace(".", "").replace(",", ".")
        if "," in raw or re.fullmatch(r"\d{1,3}(?:\.\d{3})+", raw)
        else raw
    )


def canonical_claim(claim: Claim) -> Claim:
    value, unit = claim
    if unit in {"kg", "L"}:
        return (format((Decimal(value) * 1000).normalize(), "f"), "g" if unit == "kg" else "mL")
    return (value if value == "bivolt" else format(Decimal(value).normalize(), "f"), unit)


def supported_claims(text: str) -> set[Claim]:
    # Independent numeric scan for hard attributes, in addition to general units.
    claims = {canonical_claim(c) for c in technical_claims(text)}
    for match in _FIGURE.finditer(text):
        value, unit = Decimal(match[1].replace(",", ".")), match[2].lower()
        if unit in {"v", "volt", "volts"}:
            claims.add((format(value.normalize(), "f"), "V"))
        elif unit in {"w", "watt", "watts", "kw", "quilowatt", "quilowatts"}:
            factor = 1000 if unit in {"kw", "quilowatt", "quilowatts"} else 1
            claims.add((format((value * factor).normalize(), "f"), "W"))
        elif unit in {"l", "litro", "litros", "ml", "mililitro", "mililitros"}:
            factor = 1000 if unit in {"l", "litro", "litros"} else 1
            claims.add((format((value * factor).normalize(), "f"), "mL"))
    return claims


def calculate_retrieval_precision(
    retrieved_ids: list[str],
    relevant_ids: list[str],
) -> tuple[float | None, float, float]:
    if not relevant_ids or len(relevant_ids) != len(set(relevant_ids)):
        raise ValueError("Retrieval requires nonempty unique relevant UUIDs")
    if len(retrieved_ids) != len(set(retrieved_ids)):
        raise ValueError("Duplicate retrieved UUIDs cannot inflate retrieval scores")
    relevant = set(relevant_ids)
    precision = len(set(retrieved_ids) & relevant) / len(retrieved_ids) if retrieved_ids else 0.0
    recall = len(set(retrieved_ids) & relevant) / len(relevant)
    p5 = len(set(retrieved_ids[:TOP_K]) & relevant) / TOP_K if len(relevant) >= TOP_K else None
    return p5, precision, recall


def _scope(clause: str, position: int, skus: list[str], primary: str) -> str:
    mentions = [
        (m.start(), sku)
        for sku in skus
        for m in re.finditer(re.escape(sku), clause)
        if m.start() <= position
    ]
    mentions.extend(
        (m.start(), m.group())
        for m in _SKU.finditer(clause)
        if m.start() <= position and any(c.isdigit() for c in m.group())
    )
    return max(mentions)[1] if mentions else primary


def _catalog_claims(product: CatalogProduct | None, evidence: str) -> set[Claim]:
    claims = supported_claims(evidence)
    if product is None:
        return claims
    # SQL owns these attributes; stale manual/header values never authorize them.
    claims = {c for c in claims if c[1] not in {"V", "W", "mL", "BRL"}}
    if product.voltage == "BIVOLT":
        claims.update({("127", "V"), ("220", "V"), ("bivolt", "V")})
    elif product.voltage != "N/A":
        claims.add((product.voltage[:-1], "V"))
    if product.power_watts is not None:
        claims.add((str(product.power_watts), "W"))
    if product.capacity_liters is not None:
        claims.add((format((product.capacity_liters * 1000).normalize(), "f"), "mL"))
    return claims


def technical_violations(
    answer: str,
    evidence_by_sku: dict[str, str],
    citations: list[tuple[str, str, int]],
    *,
    primary_sku: str,
    products: dict[str, CatalogProduct] | None = None,
    evidence_by_page: dict[tuple[str, str, int], str] | None = None,
) -> list[str]:
    """Conservative factual tripwire; no ground truth or user question enters this check."""
    products = products or {}
    violations: list[str] = []
    for mark in CITATION.finditer(answer):
        sku = _scope(answer, mark.start(), list(evidence_by_sku), primary_sku)
        title, page = mark[1].strip(), int(mark[2])
        if (sku, title, page) not in citations:
            violations.append(f"Unsupported citation for {sku}: {title}, p. {page}")
        if evidence_by_page is not None:
            prefix = CITATION.sub("", answer[: mark.start()])
            before = re.split(r"(?<!\d)[.!?;\n]|[.!?;\n](?!\d)", prefix)[-1]
            before = re.sub(r"^\s*SKU [A-Za-z0-9_-]+:\s*", "", before)
            page_text = evidence_by_page.get((sku, title, page), "")
            claims = supported_claims(before)
            literal = " ".join(re.findall(r"\w+", normalize(before)))
            normalized_page = " ".join(re.findall(r"\w+", normalize(page_text)))
            if (claims and not claims <= supported_claims(page_text)) or (
                not claims and (not literal or literal not in normalized_page)
            ):
                violations.append(f"Citation page does not support statement: {sku}, p. {page}")
    clean = CITATION.sub("", answer)
    # Preserve decimal points; clauses keep negation local instead of disabling a whole answer.
    clauses = re.split(r"(?<!\d)[.!?;\n]|[.!?;\n](?!\d)", clean)
    for clause in clauses:
        violations.extend(_clause_violations(clause, evidence_by_sku, products, primary_sku))
    return violations


def _clause_violations(
    clause: str,
    evidence: dict[str, str],
    products: dict[str, CatalogProduct],
    primary: str,
) -> list[str]:
    violations: list[str] = []
    masked = clause
    for sku in evidence:
        masked = masked.replace(sku, " " * len(sku))
    positions = [
        (m.start(), m.group()) for regex in (_FIGURE, _BIVOLT) for m in regex.finditer(masked)
    ]
    for start, raw in positions:
        sku = _scope(clause, start, list(evidence), primary)
        supported = _catalog_claims(products.get(sku), evidence.get(sku, ""))
        denied = bool(DENIAL.search(normalize(masked[:start]).strip()))
        # Attribute/unit binding is checked independently of mere value membership.
        prefix = normalize(masked[:start])
        if re.search(r"(?:voltagem|tensao|funciona|opera)(?: e| de| em)?\s*$", prefix) and not any(
            unit == "V" for _, unit in supported_claims(raw)
        ):
            violations.append(f"Wrong voltage unit: {raw}")
        if re.search(r"potencia(?: e| de)?\s*$", prefix) and not any(
            unit == "W" for _, unit in supported_claims(raw)
        ):
            violations.append(f"Wrong power unit: {raw}")
        if re.search(r"capacidade(?: e| de)?\s*$", prefix) and not any(
            unit == "mL" for _, unit in supported_claims(raw)
        ):
            violations.append(f"Wrong capacity unit: {raw}")
        for claim in supported_claims(raw):
            if (claim not in supported and not denied) or (claim in supported and denied):
                violations.append(f"Unsupported/contradicted {sku} claim: {raw}")
    for match in [*PRICE.finditer(masked), *REALS.finditer(masked)]:
        sku = _scope(clause, match.start(), list(evidence), primary)
        prices = (
            {products[sku].price}
            if sku in products
            else {number(p) for p in PRICE.findall(evidence.get(sku, ""))}
        )
        if number(match.group(1)) not in prices:
            violations.append(f"Unsupported {sku} price: {match.group()}")
    return violations


def business_violations(
    turn: ObservedTurn, fixture: GoldenSetFixture, relations: list[ProductRelation] | None = None
) -> list[str]:
    violations: list[str] = []
    base = turn.products.get(fixture.input_filters.sku)
    if base is None:
        return ["Missing current catalog snapshot"]
    requested = fixture.input_filters.voltage
    if len(turn.offers) > 3 or len({offer.role for offer in turn.offers}) != len(turn.offers):
        violations.append("More than three cards or repeated recommendation role")
    if len({offer.sku for offer in turn.offers}) != len(turn.offers):
        violations.append("Duplicate offer SKU")
    for offer in turn.offers:
        product = turn.products.get(offer.sku)
        if product is None or not product.is_active or product.stock_quantity <= 0:
            violations.append(f"Unavailable offer: {offer.sku}")
            continue
        if offer.price != product.price:
            violations.append(f"Stale/fabricated price: {offer.sku}")
        if requested is not None and product.voltage not in {requested, "BIVOLT", "N/A"}:
            violations.append(f"Incompatible buying voltage: {offer.sku}")
        if offer.stock_quantity is not None and offer.stock_quantity != product.stock_quantity:
            violations.append(f"Fabricated stock: {offer.sku}")
        if offer.voltage is not None and offer.voltage != product.voltage:
            violations.append(f"Fabricated voltage: {offer.sku}")
        if offer.role == "PRIMARY" and product.sku != base.sku:
            violations.append("PRIMARY differs from consulted SKU")
        if offer.role != "PRIMARY" and product.voltage not in {
            requested or base.voltage,
            "BIVOLT",
            "N/A",
        }:
            violations.append(f"Incompatible secondary offer: {offer.sku}")
        if offer.role == "CROSS_SELL" and (
            product.price > base.price * CROSS_SELL_MAX_PRICE_RATIO
            or not any(
                r.base_sku == base.sku
                and r.related_sku == product.sku
                and r.relation_type == "CROSS_SELL"
                for r in relations or []
            )
        ):
            violations.append(f"Unverified/overpriced cross-sell: {offer.sku}")
        if offer.role == "UPSELL" and not (
            base.price < product.price <= base.price * UPSELL_MAX_PRICE_RATIO
            and base.category == product.category
            and base.subcategory == product.subcategory
            and (
                product.tier_rank > base.tier_rank
                or (
                    product.capacity_liters is not None
                    and base.capacity_liters is not None
                    and product.capacity_liters > base.capacity_liters
                )
            )
        ):
            violations.append(f"Invalid upsell price/category: {offer.sku}")
    actual = {(o.sku, o.role) for o in turn.offers}
    if any((o.sku, o.role) not in actual for o in fixture.expected_offers):
        violations.append("Required recommendation missing from published events (B04 integration)")
    if fixture.offer_policy == "exact" and actual != {
        (o.sku, o.role) for o in fixture.expected_offers
    }:
        violations.append("Published offers differ from the requested purchase scenario")
    if base.stock_quantity == 0 and not turn.offers:
        text = normalize(turn.answer)
        if re.search(r"\b(?:compre|finaliz\w*|pronta entrega|temos disponivel)\b", text):
            violations.append("Purchase encouraged for zero-stock scenario")
    return violations


def _average_gate(name: str, values: list[float | None], floor: float) -> GateResult:
    valid = bool(values) and all(v is not None and math.isfinite(v) and 0 <= v <= 1 for v in values)
    mean = sum(v for v in values if v is not None) / len(values) if valid else None
    return GateResult(
        metric_name=name,
        value=mean,
        threshold=floor,
        denominator=len(values),
        passed=mean is not None and mean >= floor,
        reason="" if valid else "Missing, invalid or absent applicable samples",
    )


def aggregate_macro_metrics(
    results: list[EvalCaseResult], identity: RunIdentity
) -> EvaluationReport:
    factual = [r for r in results if "faithfulness" in r.expected_metrics]
    retrieval = [r for r in results if "retrieval" in r.expected_metrics]
    relevant = [r for r in results if "answer_relevance" in r.expected_metrics]
    faithfulness = _average_gate(
        "Faithfulness", [r.faithfulness for r in factual], FAITHFULNESS_FLOOR
    )
    precision = _average_gate(
        "Retrieval precision",
        [
            r.precision_at_5 if r.precision_at_5 is not None else r.precision_returned
            for r in retrieval
        ],
        RETRIEVAL_FLOOR,
    )
    recall = _average_gate(
        "Recall", [r.recall for r in retrieval if r.precision_at_5 is None], RETRIEVAL_FLOOR
    )
    # P@5 fixtures do not require a full relevant-set recall, per spec section 5.
    if retrieval and all(r.precision_at_5 is not None for r in retrieval):
        recall.reason, recall.passed = "Not applicable: all retrieval cases use P@5", True
    relevance = _average_gate(
        "Answer relevance", [r.answer_relevance for r in relevant], RELEVANCE_FLOOR
    )
    actions = _average_gate("Action accuracy", [float(r.action_matched) for r in results], 1.0)
    business = _average_gate(
        "Business rules", [float(not r.business_violations) for r in results], 1.0
    )
    critical = _average_gate(
        "No critical published violations",
        [float(not r.technical_violations) for r in results],
        1.0,
    )
    failure_rate = (
        sum(bool(r.technical_violations) for r in results) / len(results) if results else None
    )
    hallucination = GateResult(
        metric_name="Technical hallucination rate",
        value=failure_rate,
        threshold=HALLUCINATION_CEILING,
        comparator="<=",
        denominator=len(results),
        passed=failure_rate is not None and failure_rate <= HALLUCINATION_CEILING,
    )
    errors = [f"{r.case_id}: {error}" for r in results for error in r.errors]
    integrity = (
        identity.mode == "live"
        and identity.corpus_verified
        and identity.clean_checkout
        and bool(identity.revision)
        and bool(identity.fingerprint)
        and identity.integrated_b04
        and bool(identity.judge_model)
        and identity.judge_model != identity.generator_model
        and {r.case_id for r in results} == {f"RAGAS-GS-{i:02}" for i in range(1, 51)}
        and all(r.observation is not None for r in results)
        and len(results) == identity.expected_cases == 50
        and not errors
    )
    execution = GateResult(
        metric_name="Verified full live execution",
        value=float(integrity),
        threshold=1.0,
        denominator=len(results),
        passed=integrity,
        reason="" if integrity else "Offline, partial, dirty, unverified or failed execution",
    )
    audit = GateResult(
        metric_name="PO source audit approval",
        value=float(identity.po_audit_approved),
        threshold=1,
        denominator=50,
        passed=identity.po_audit_approved,
        reason="Seed demonstration sources still require recorded human audit"
        if not identity.po_audit_approved
        else "",
    )
    gates = [
        faithfulness,
        precision,
        recall,
        relevance,
        actions,
        business,
        critical,
        hallucination,
        execution,
        audit,
    ]
    passed = all(g.passed for g in gates)
    return EvaluationReport(
        identity=identity,
        total_cases=identity.expected_cases,
        evaluated_cases=len(results),
        faithfulness_macro=faithfulness.value,
        precision_macro=precision.value,
        recall_macro=recall.value,
        answer_relevance_macro=relevance.value,
        gates=gates,
        all_gates_passed=passed,
        status="PASSED" if passed else ("PENDING" if identity.mode != "live" else "FAILED"),
        case_results=results,
        errors=errors,
        exclusions={
            metric: [
                f"{r.case_id}: expected action {r.expected_action}"
                for r in results
                if metric not in r.expected_metrics
            ]
            for metric in ("faithfulness", "answer_relevance", "retrieval")
        },
    )
