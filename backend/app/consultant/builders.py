"""Pure deterministic answer builders for every non-LLM route (spec §4 and §11 A3)."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal
from uuid import UUID

from app.consultant.conversation import Slots
from app.consultant.evidence import GameRow, KbFactHit, KbMeasure, webcam_capability
from app.models.schemas import CatalogProduct, RetrievedChunk
from app.recommendation.cards import ProductCard, brl, build_card

GREETING_MESSAGE = (
    "Olá! Posso ajudar a escolher um produto, comparar opções ou tirar dúvidas técnicas. "
    "O que você procura?\n"
)
NO_COMPARISON_SET_MESSAGE = (
    "Ainda não mostrei opções suficientes para comparar. "
    "Me diga que tipo de produto você procura.\n"
)
GAME_FIT_GENERAL_INFO = (
    "Informação geral: o desempenho real varia com drivers, atualizações do jogo e "
    "configurações gráficas."
)
GAME_FIT_MISSING_BENCHMARK = (
    "Não encontrei nas fontes do catálogo um teste que confirme o desempenho solicitado. "
    "Se você souber os requisitos, posso informar as especificações do PC para a comparação.\n"
)
STREAM_FIT_GENERAL_INFO = (
    "Informação geral: a qualidade final da live também depende da sua conexão de internet "
    "e do computador usado na transmissão."
)
DIMENSION_FIT_GENERAL_INFO = (
    "Informação geral: confira também a profundidade e o caminho até a sala, como portas e "
    "corredores."
)
FIXED_GENERAL_INFORMATION: tuple[str, ...] = (
    GAME_FIT_GENERAL_INFO,
    STREAM_FIT_GENERAL_INFO,
    DIMENSION_FIT_GENERAL_INFO,
)


@dataclass(frozen=True)
class ConsultantAnswer:
    sentences: tuple[str, ...]
    cited: tuple[RetrievedChunk, ...]
    cards: tuple[ProductCard, ...]
    intent: str


def clarify_product_message(first_sku: str) -> str:
    return (
        f"Sobre qual dos produtos mostrados? Cite o SKU, por exemplo SKU {first_sku}, "
        "ou abra a página do produto.\n"
    )


def pt_br_decimal(value: Decimal | float | int) -> str:
    return format(Decimal(str(value)).normalize(), "f").replace(".", ",")


def voltage_text(voltage: str) -> str | None:
    if voltage == "BIVOLT":
        return "bivolt"
    if voltage in {"127V", "220V"}:
        return voltage
    return None


def key_specs(product: CatalogProduct) -> str:
    specs = product.specs_json
    if product.subcategory in {"PCs Gamer", "Notebooks Gamer"} or product.category == "Computadores":
        parts: list[str] = []
        if specs.get("placa_de_video"):
            parts.append(str(specs["placa_de_video"]))
        if specs.get("memoria_ram_gb") is not None:
            parts.append(f"{pt_br_decimal(specs['memoria_ram_gb'])} GB de RAM")  # type: ignore[arg-type]
        return ", ".join(parts)
    if product.subcategory == "Monitores Gamer" or product.category == "Monitores":
        parts = []
        if specs.get("tela_polegadas") is not None:
            parts.append(f"{pt_br_decimal(specs['tela_polegadas'])} polegadas")  # type: ignore[arg-type]
        if specs.get("taxa_atualizacao_hz") is not None:
            parts.append(f"{pt_br_decimal(specs['taxa_atualizacao_hz'])} Hz")  # type: ignore[arg-type]
        return ", ".join(parts)
    if product.subcategory == "Webcams":
        res = specs.get("resolucao")
        fps = specs.get("fps")
        if res and fps is not None:
            return f"resolução {res} a {fps} fps"
        if res:
            return f"resolução {res}"
        if fps is not None:
            return f"{fps} fps"
        return ""
    if product.subcategory == "Sofás" or product.category == "Móveis":
        parts = []
        if specs.get("largura_cm") is not None:
            parts.append(f"{pt_br_decimal(specs['largura_cm'])} cm de largura")  # type: ignore[arg-type]
        if specs.get("lugares") is not None:
            parts.append(f"{specs['lugares']} lugares")
        return ", ".join(parts)
    parts = []
    if product.capacity_liters is not None:
        parts.append(f"{pt_br_decimal(product.capacity_liters)} L")
    if product.power_watts is not None:
        parts.append(f"{product.power_watts} W")
    return ", ".join(parts)


def _option_card(product: CatalogProduct, justification: str | None = None) -> ProductCard:
    specs = key_specs(product)
    card_justification = (
        justification
        if justification is not None
        else (f"{specs}." if specs else f"Disponível em estoque por {brl(product.price)}.")
    )
    return build_card(product, "OPTION", card_justification)


def _dedup_chunks(chunks: Sequence[RetrievedChunk]) -> tuple[RetrievedChunk, ...]:
    seen: set[UUID] = set()
    ordered: list[RetrievedChunk] = []
    for chunk in chunks:
        if chunk.chunk_id not in seen:
            seen.add(chunk.chunk_id)
            ordered.append(chunk)
    return tuple(ordered)


def _sold_out_suffix(product: CatalogProduct) -> str:
    return " (esgotado no momento)" if not product.is_active or product.stock_quantity <= 0 else ""


def _warranty_and_rating(product: CatalogProduct) -> tuple[str, str]:
    specs = product.specs_json
    raw_warranty = specs.get("garantia_meses")
    warranty = (
        f"garantia de {raw_warranty} meses"
        if type(raw_warranty) is int and raw_warranty > 0
        else "garantia não informada"
    )
    raw_rating = specs.get("avaliacao_media")
    raw_count = specs.get("avaliacoes_total")
    rating = (
        f"avaliação {pt_br_decimal(raw_rating)} de 5 em {raw_count} avaliações"
        if isinstance(raw_rating, (int, float, Decimal))
        and not isinstance(raw_rating, bool)
        and type(raw_count) is int
        and raw_count > 0
        else "sem avaliações no catálogo"
    )
    return warranty, rating


def discovery_answer(
    options: Sequence[CatalogProduct],
    slots: Slots,
    *,
    game_rows: Mapping[str, GameRow | None],
    game_fact: KbFactHit | None,
    relaxed: CatalogProduct | None,
    categories_in_stock: Sequence[tuple[str, str]],
) -> ConsultantAnswer:
    if slots.category is None and not options:
        unique_categories = list(dict.fromkeys(cat for cat, _ in categories_in_stock))
        joined = ", ".join(unique_categories) if unique_categories else "Computadores, Monitores, Móveis"
        return ConsultantAnswer(
            sentences=(
                f"Posso ajudar com estas categorias em estoque: {joined}. Qual delas você procura?\n",
            ),
            cited=(),
            cards=(),
            intent="PURCHASE_INTENT",
        )

    subcats_label = (
        " e ".join(slots.category.subcategories)
        if slots.category and slots.category.subcategories
        else (slots.category.category if slots.category else "produtos")
    )
    filter_tail = ""
    if slots.budget_max is not None:
        filter_tail += f" até {brl(slots.budget_max)}"
    if slots.voltage is not None:
        filter_tail += f" que funcionam em {slots.voltage}"
    scope = (f" em {subcats_label}" if slots.category else "") + filter_tail

    in_stock = [p for p in options if p.is_active and p.stock_quantity > 0]
    if not in_stock:
        sentences = [f"Não encontrei {subcats_label} em estoque{filter_tail}.\n"]
        if relaxed is not None and relaxed.is_active and relaxed.stock_quantity > 0:
            sentences.append(
                f"Sem o limite de orçamento, a opção mais barata em estoque é SKU {relaxed.sku}: "
                f"{relaxed.name}, {brl(relaxed.price)}.\n"
            )
        return ConsultantAnswer(
            sentences=tuple(sentences),
            cited=(),
            cards=(),
            intent="PURCHASE_INTENT",
        )

    count = len(in_stock)
    noun = "opção" if count == 1 else "opções"
    sentences = [
        f"Encontrei {count} {noun} em estoque{scope}, do menor para o maior preço:\n"
    ]
    cited: list[RetrievedChunk] = []

    for product in in_stock:
        parts = [f"SKU {product.sku}: {product.name}", brl(product.price)]
        specs = key_specs(product)
        if specs:
            parts.append(specs)
        vtext = voltage_text(product.voltage)
        if vtext:
            parts.append(f"voltagem {vtext}")
        sentences.append("- " + ", ".join(parts) + ".\n")

        if slots.game is not None and game_fact is None:
            row = game_rows.get(product.sku)
            if row is not None:
                sentences.append(
                    f"  {slots.game}: {row.fps} fps em {row.resolution}, predefinição "
                    f"{row.preset} [Fonte: {row.chunk.manual_title}, p. {row.chunk.page_number}].\n"
                )
                cited.append(row.chunk)
            else:
                sentences.append(f"  {slots.game}: desempenho não informado no manual.\n")

    if game_fact is not None:
        sentences.append(
            f"Lembrando: {game_fact.sentence} "
            f"[Fonte: {game_fact.chunk.manual_title}, p. {game_fact.chunk.page_number}].\n"
        )
        cited.append(game_fact.chunk)

    if slots.budget_max is None:
        sentences.append("Para refinar, me diga o uso principal e o orçamento máximo.\n")

    cards = tuple(_option_card(product) for product in in_stock)
    return ConsultantAnswer(
        sentences=tuple(sentences),
        cited=_dedup_chunks(cited),
        cards=cards,
        intent="PURCHASE_INTENT",
    )


def game_fit_answer(
    targets: Sequence[CatalogProduct],
    game: str | None,
    rows: Mapping[str, GameRow | None],
    platform: Sequence[KbFactHit],
    alias: KbFactHit | None,
    alternative: tuple[CatalogProduct, GameRow] | None,
    consoles_in_catalog: bool,
) -> ConsultantAnswer:
    if game is None:
        return ConsultantAnswer(
            sentences=(GAME_FIT_MISSING_BENCHMARK,), cited=(), cards=(), intent="TECHNICAL_QA"
        )

    sentences: list[str] = []
    cited: list[RetrievedChunk] = []
    cards: list[ProductCard] = []

    if platform:
        for hit in platform:
            sentences.append(
                f"{hit.sentence} [Fonte: {hit.chunk.manual_title}, p. {hit.chunk.page_number}].\n"
            )
            cited.append(hit.chunk)
        sentences.append(f"Por isso, nenhum computador do catálogo roda {game} hoje.\n")
        if not consoles_in_catalog:
            sentences.append("O catálogo ativo não tem consoles.\n")
        sentences.append(
            "Se quiser, mostro o desempenho informado nos manuais em outros jogos, como GTA V e Roblox.\n"
        )
        return ConsultantAnswer(
            sentences=tuple(sentences),
            cited=_dedup_chunks(cited),
            cards=(),
            intent="TECHNICAL_QA",
        )

    if alias is not None:
        sentences.append(
            f"{alias.sentence} [Fonte: {alias.chunk.manual_title}, p. {alias.chunk.page_number}].\n"
        )
        cited.append(alias.chunk)

    effective_game = "GTA V" if game == "GTA RP" else game
    confirmation = "" if game == "GTA RP" else "sim, "
    for product in targets:
        row = rows.get(product.sku)
        if row is not None:
            sentences.append(
                f"SKU {product.sku}: {confirmation}o manual informa {row.fps} fps em {effective_game} "
                f"a {row.resolution}, predefinição {row.preset} "
                f"[Fonte: {row.chunk.manual_title}, p. {row.chunk.page_number}].\n"
            )
            cited.append(row.chunk)
        else:
            sentences.append(
                f"SKU {product.sku}: o manual não informa desempenho em {effective_game}, "
                "então não confirmo que roda.\n"
            )

    if len(targets) == 1 and rows.get(targets[0].sku) is None and alternative is not None:
        alt_product, alt_row = alternative
        sentences.append(
            f"Este outro tem desempenho informado em {effective_game}: SKU {alt_product.sku}: "
            f"{alt_row.fps} fps a {alt_row.resolution}, predefinição {alt_row.preset} "
            f"[Fonte: {alt_row.chunk.manual_title}, p. {alt_row.chunk.page_number}].\n"
        )
        cited.append(alt_row.chunk)
        if alt_product.is_active and alt_product.stock_quantity > 0:
            cards.append(_option_card(alt_product))

    if game == "GTA RP" and (any(rows.values()) or alternative is not None):
        sentences.append(
            "O benchmark é de GTA V. O desempenho em servidores de GTA RP não foi medido "
            "nas fontes consultadas.\n"
        )
    sentences.append(f"{GAME_FIT_GENERAL_INFO}\n")
    return ConsultantAnswer(
        sentences=tuple(sentences),
        cited=_dedup_chunks(cited),
        cards=tuple(cards),
        intent="TECHNICAL_QA",
    )


def stream_fit_answer(
    target: CatalogProduct | None,
    height: KbMeasure,
    fps: KbMeasure,
    matches: Sequence[CatalogProduct],
) -> ConsultantAnswer:
    req_h = int(height.value)
    req_f = int(fps.value)
    sentences = [
        f"A Twitch recomenda transmitir em até {req_h}p a {req_f} fps "
        f"[Fonte: {height.chunk.manual_title}, p. {height.chunk.page_number}].\n"
    ]
    cited = [height.chunk, fps.chunk]
    cards: list[ProductCard] = []
    in_stock_matches = [
        p
        for p in matches
        if p.is_active
        and p.stock_quantity > 0
        and (cap := webcam_capability(p)) is not None
        and cap[0] >= req_h
        and cap[1] >= req_f
    ]

    if target is not None:
        res = target.specs_json.get("resolucao")
        target_fps = target.specs_json.get("fps")
        sentences.append(
            f"SKU {target.sku}: resolução {res} a {target_fps} fps, segundo a ficha técnica.\n"
        )
        cap = webcam_capability(target)
        if cap is not None and cap[0] >= req_h and cap[1] >= req_f:
            sentences.append("Esta câmera atende à qualidade máxima recomendada pela Twitch.\n")
        else:
            if cap is None or cap[0] < req_h:
                sentences.append(
                    "Esta câmera não atende à qualidade máxima recomendada pela Twitch: "
                    f"a resolução fica abaixo de {req_h}p.\n"
                )
            else:
                sentences.append(
                    "Esta câmera não atende à qualidade máxima recomendada pela Twitch: "
                    f"fica em {cap[1]} fps, abaixo de {req_f} fps.\n"
                )
            alternatives = [p for p in in_stock_matches if p.sku != target.sku]
            if alternatives:
                alt = min(alternatives, key=lambda p: (p.price, p.sku))
                alt_res = alt.specs_json.get("resolucao")
                alt_fps = alt.specs_json.get("fps")
                sentences.append(
                    f"Este outro atende: SKU {alt.sku}: resolução {alt_res} a {alt_fps} fps, "
                    f"{brl(alt.price)}.\n"
                )
                cards.append(_option_card(alt))
            else:
                sentences.append(
                    "Não há outra webcam em estoque que atenda a essa recomendação.\n"
                )
    else:
        if in_stock_matches:
            for product in in_stock_matches:
                sentences.append(
                    f"- SKU {product.sku}: {product.name}, {brl(product.price)}, "
                    f"{key_specs(product)}.\n"
                )
                cards.append(_option_card(product))
        else:
            sentences.append("Não há outra webcam em estoque que atenda a essa recomendação.\n")

    sentences.append(f"{STREAM_FIT_GENERAL_INFO}\n")
    return ConsultantAnswer(
        sentences=tuple(sentences),
        cited=_dedup_chunks(cited),
        cards=tuple(cards),
        intent="TECHNICAL_QA",
    )


def dimension_fit_answer(
    target: CatalogProduct | None,
    room_cm: Decimal | None,
    clearance: KbMeasure,
    matches: Sequence[CatalogProduct],
) -> ConsultantAnswer:
    if room_cm is None:
        return ConsultantAnswer(
            sentences=(
                "Qual é a largura livre do espaço onde o sofá vai ficar, em metros ou centímetros?\n",
            ),
            cited=(),
            cards=(),
            intent="TECHNICAL_QA",
        )

    sentences: list[str] = []
    cited = [clearance.chunk]
    cards: list[ProductCard] = []
    c_val = clearance.value
    c_str = pt_br_decimal(c_val)
    m_str = pt_br_decimal(room_cm)

    def _width(product: CatalogProduct) -> Decimal:
        return Decimal(str(product.specs_json["largura_cm"]))

    fitting_candidates = sorted(
        (
            p
            for p in matches
            if p.is_active
            and p.stock_quantity > 0
            and p.specs_json.get("largura_cm") is not None
            and _width(p) + 2 * c_val <= room_cm
            and (target is None or p.sku != target.sku)
        ),
        key=lambda p: (-_width(p), p.price, p.sku),
    )

    if target is not None:
        w_val = _width(target)
        d_val = Decimal(str(target.specs_json["profundidade_cm"]))
        needed_val = w_val + 2 * c_val
        sentences.append(
            f"SKU {target.sku}: largura de {pt_br_decimal(w_val)} cm, "
            f"profundidade de {pt_br_decimal(d_val)} cm.\n"
        )
        sentences.append(
            f"A orientação é deixar pelo menos {c_str} cm livres de cada lado do sofá "
            f"[Fonte: {clearance.chunk.manual_title}, p. {clearance.chunk.page_number}], "
            f"então ele precisa de {pt_br_decimal(needed_val)} cm.\n"
        )
        if needed_val <= room_cm:
            sentences.append(f"Cabe nos {m_str} cm informados, com a folga recomendada.\n")
        elif w_val <= room_cm:
            sentences.append(f"Cabe nos {m_str} cm informados, mas sem a folga recomendada.\n")
        else:
            sentences.append(f"Não cabe nos {m_str} cm informados.\n")

        if needed_val > room_cm and fitting_candidates:
            alt = fitting_candidates[0]
            w2 = pt_br_decimal(_width(alt))
            lugares = alt.specs_json.get("lugares")
            sentences.append(
                f"Este outro cabe com folga: SKU {alt.sku}: largura de {w2} cm, "
                f"{lugares} lugares, {brl(alt.price)}.\n"
            )
            cards.append(_option_card(alt))
    else:
        sentences.append(
            f"A orientação é deixar pelo menos {c_str} cm livres de cada lado do sofá "
            f"[Fonte: {clearance.chunk.manual_title}, p. {clearance.chunk.page_number}].\n"
        )
        if fitting_candidates:
            for alt in fitting_candidates:
                w2 = pt_br_decimal(_width(alt))
                lugares = alt.specs_json.get("lugares")
                sentences.append(
                    f"Este outro cabe com folga: SKU {alt.sku}: largura de {w2} cm, "
                    f"{lugares} lugares, {brl(alt.price)}.\n"
                )
                cards.append(_option_card(alt))
        else:
            sentences.append(f"Não cabe nos {m_str} cm informados.\n")

    sentences.append(f"{DIMENSION_FIT_GENERAL_INFO}\n")
    return ConsultantAnswer(
        sentences=tuple(sentences),
        cited=_dedup_chunks(cited),
        cards=tuple(cards),
        intent="TECHNICAL_QA",
    )


def set_voltage_answer(
    products: Sequence[CatalogProduct],
    voltage: Literal["127V", "220V"] | None,
) -> ConsultantAnswer:
    target_v: Literal["127V", "220V"] = voltage or "127V"
    total = len(products)
    compatible_count = sum(1 for p in products if p.voltage in {target_v, "BIVOLT"})

    if compatible_count == total:
        header = f"Sim: os {total} produtos mostrados funcionam em {target_v}.\n"
    elif compatible_count > 0:
        header = f"Não: {compatible_count} dos {total} produtos mostrados funcionam em {target_v}.\n"
    else:
        header = f"Não: nenhum dos {total} produtos mostrados funciona em {target_v}.\n"

    sentences = [header]
    cards: list[ProductCard] = []
    for product in products:
        sold_out = _sold_out_suffix(product)
        if product.voltage == "BIVOLT":
            sentences.append(
                f"- SKU {product.sku}: bivolt, funciona em {target_v}{sold_out}.\n"
            )
        elif product.voltage == target_v:
            sentences.append(
                f"- SKU {product.sku}: {target_v}, funciona em {target_v}{sold_out}.\n"
            )
        elif product.voltage == "N/A":
            sentences.append(
                f"- SKU {product.sku}: não é ligado diretamente na tomada{sold_out}.\n"
            )
        else:
            sentences.append(
                f"- SKU {product.sku}: {product.voltage}, não deve ser ligado em {target_v}{sold_out}.\n"
            )
        if product.voltage in {target_v, "BIVOLT"} and product.is_active and product.stock_quantity > 0:
            cards.append(_option_card(product, f"Funciona em {target_v}."))

    return ConsultantAnswer(
        sentences=tuple(sentences),
        cited=(),
        cards=tuple(cards),
        intent="PRODUCT_COMPARISON",
    )


def price_rank_answer(
    products: Sequence[CatalogProduct],
    referent: CatalogProduct | None,
    direction: Literal["cheapest", "priciest"],
    from_peers: bool,
) -> ConsultantAnswer:
    total = len(products)
    min_price = min(p.price for p in products)
    max_price = max(p.price for p in products)
    cheapest_list = [p for p in products if p.price == min_price]
    priciest_list = [p for p in products if p.price == max_price]
    subcat = referent.subcategory if referent is not None else products[0].subcategory
    prefix = f"Comparando com {subcat} em estoque: " if from_peers else ""

    if direction == "cheapest":
        if len(cheapest_list) > 1:
            tied = " e ".join(f"SKU {p.sku}" for p in cheapest_list)
            body = f"{tied} empatam no menor preço, {brl(min_price)}.\n"
        else:
            cheapest = cheapest_list[0]
            if referent is not None:
                if referent.sku == cheapest.sku:
                    body = (
                        f"Sim: SKU {referent.sku} é o mais barato dos {total} comparados, "
                        f"por {brl(referent.price)}.\n"
                    )
                else:
                    body = (
                        f"Não. Este produto aqui é mais barato: SKU {cheapest.sku}, "
                        f"por {brl(cheapest.price)}, contra {brl(referent.price)} do SKU {referent.sku}.\n"
                    )
            else:
                priciest = priciest_list[0]
                body = (
                    f"O mais barato dos {total} comparados é SKU {cheapest.sku}, "
                    f"por {brl(cheapest.price)}; o mais caro é SKU {priciest.sku}, "
                    f"por {brl(priciest.price)}.\n"
                )
    else:
        if len(priciest_list) > 1:
            tied = " e ".join(f"SKU {p.sku}" for p in priciest_list)
            body = f"{tied} empatam no maior preço, {brl(max_price)}.\n"
        else:
            priciest = priciest_list[0]
            if referent is not None:
                if referent.sku == priciest.sku:
                    body = (
                        f"Sim: SKU {referent.sku} é o mais caro dos {total} comparados, "
                        f"por {brl(referent.price)}.\n"
                    )
                else:
                    body = (
                        f"Não. Este produto aqui é mais caro: SKU {priciest.sku}, "
                        f"por {brl(priciest.price)}, contra {brl(referent.price)} do SKU {referent.sku}.\n"
                    )
            else:
                cheapest = cheapest_list[0]
                body = (
                    f"O mais caro dos {total} comparados é SKU {priciest.sku}, "
                    f"por {brl(priciest.price)}; o mais barato é SKU {cheapest.sku}, "
                    f"por {brl(cheapest.price)}.\n"
                )

    cheapest_in_stock = min(
        (p for p in products if p.is_active and p.stock_quantity > 0),
        key=lambda p: (p.price, p.sku),
        default=None,
    )
    cards = (_option_card(cheapest_in_stock),) if cheapest_in_stock is not None else ()
    return ConsultantAnswer(
        sentences=(f"{prefix}{body}",),
        cited=(),
        cards=cards,
        intent="PRODUCT_COMPARISON",
    )


def comparison_answer(
    products: Sequence[CatalogProduct],
    game_rows: Mapping[str, GameRow | None],
    game: str | None,
) -> ConsultantAnswer:
    sentences = ["Não há um melhor absoluto; comparo pelos dados do catálogo:\n"]
    cited: list[RetrievedChunk] = []

    for product in products:
        parts = [f"SKU {product.sku}: {brl(product.price)}"]
        specs = key_specs(product)
        if specs:
            parts.append(specs)
        vtext = voltage_text(product.voltage)
        if vtext:
            parts.append(f"voltagem {vtext}")
        warranty, rating = _warranty_and_rating(product)
        parts.extend((warranty, rating))
        sentences.append("- " + ", ".join(parts) + f"{_sold_out_suffix(product)}.\n")

    min_price = min(p.price for p in products)
    price_winners = " e ".join(f"SKU {p.sku}" for p in products if p.price == min_price)
    sentences.append(f"Menor preço: {price_winners}.\n")

    with_warranty = [
        (p, int(p.specs_json["garantia_meses"]))
        for p in products
        if type(p.specs_json.get("garantia_meses")) is int and int(p.specs_json["garantia_meses"]) > 0
    ]
    if with_warranty:
        max_w = max(w for _, w in with_warranty)
        w_winners = " e ".join(f"SKU {p.sku}" for p, w in with_warranty if w == max_w)
        sentences.append(f"Maior garantia: {w_winners}, {max_w} meses.\n")

    with_rating = [
        (p, Decimal(str(p.specs_json["avaliacao_media"])))
        for p in products
        if isinstance(p.specs_json.get("avaliacao_media"), (int, float, Decimal))
        and not isinstance(p.specs_json.get("avaliacao_media"), bool)
        and type(p.specs_json.get("avaliacoes_total")) is int
        and int(p.specs_json["avaliacoes_total"]) > 0
    ]
    if with_rating:
        max_r = max(r for _, r in with_rating)
        r_winners = " e ".join(f"SKU {p.sku}" for p, r in with_rating if r == max_r)
        sentences.append(f"Melhor avaliação média: {r_winners}, {pt_br_decimal(max_r)} de 5.\n")

    if game is not None:
        with_game = [
            (p, row)
            for p in products
            if (row := game_rows.get(p.sku)) is not None
        ]
        if with_game:
            max_fps = max(row.fps for _, row in with_game)
            fps_winners = [(p, row) for p, row in with_game if row.fps == max_fps]
            winner_skus = " e ".join(f"SKU {p.sku}" for p, _ in fps_winners)
            winner_cites = " ".join(
                f"[Fonte: {row.chunk.manual_title}, p. {row.chunk.page_number}]"
                for _, row in fps_winners
            )
            for _, row in fps_winners:
                cited.append(row.chunk)
            sentences.append(
                f"Maior desempenho informado em {game}: {winner_skus}, {max_fps} fps {winner_cites}.\n"
            )

    sentences.append(
        "Se me disser o que pesa mais para você, preço, garantia ou desempenho, indico um deles.\n"
    )
    cards = tuple(
        _option_card(p) for p in products if p.is_active and p.stock_quantity > 0
    )
    return ConsultantAnswer(
        sentences=tuple(sentences),
        cited=_dedup_chunks(cited),
        cards=cards,
        intent="PRODUCT_COMPARISON",
    )


def brand_opinion_answer(products: Sequence[CatalogProduct]) -> ConsultantAnswer:
    sentences = [
        "Não tenho dados de confiabilidade ou de defeitos por marca, então não faço ranking de marcas.\n",
        "Os critérios objetivos do catálogo para os produtos mostrados são garantia e avaliações:\n",
    ]
    for product in products:
        warranty, rating = _warranty_and_rating(product)
        sold_out = _sold_out_suffix(product)
        sentences.append(
            f"- SKU {product.sku}, marca {product.brand}: {warranty}, {rating}{sold_out}.\n"
        )
    return ConsultantAnswer(
        sentences=tuple(sentences),
        cited=(),
        cards=(),
        intent="PRODUCT_COMPARISON",
    )
