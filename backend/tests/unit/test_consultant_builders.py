"""UT-CU-09..16: exact pt-BR deterministic builder templates and OPTION cards."""

from decimal import Decimal
from uuid import uuid4

from app.consultant.builders import (
    DIMENSION_FIT_GENERAL_INFO,
    GAME_FIT_GENERAL_INFO,
    GREETING_MESSAGE,
    STREAM_FIT_GENERAL_INFO,
    brand_opinion_answer,
    clarify_product_message,
    comparison_answer,
    dimension_fit_answer,
    discovery_answer,
    game_fit_answer,
    price_rank_answer,
    set_voltage_answer,
    stream_fit_answer,
)
from app.consultant.conversation import CategoryTarget, Slots
from app.consultant.evidence import GameRow, KbFactHit, KbMeasure
from app.consultant.knowledge_facts import (
    KB_GTA6_NO_PC,
    KB_GTA6_PLATFORMS,
    KB_GTA_RP,
)
from app.models.schemas import CatalogProduct, RetrievedChunk


def _chunk(sku: str, title: str, page: int, content: str = "Evidência") -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=uuid4(),
        sku=sku,
        manual_title=title,
        page_number=page,
        content=content,
        similarity_score=1.0,
    )


PC_X3 = CatalogProduct(
    sku="PC-VX3-BIV",
    name="PC Gamer Vortex X3",
    category="Computadores",
    subcategory="PCs Gamer",
    brand="Vortex",
    price=Decimal("3499.00"),
    stock_quantity=7,
    voltage="BIVOLT",
    power_watts=500,
    tier_rank=1,
    image_url="/images/pc-vx3-biv.svg",
    checkout_url="https://example.com/pc-vx3",
    specs_json={
        "placa_de_video": "RTX 3050 6 GB",
        "memoria_ram_gb": 16,
        "garantia_meses": 12,
        "avaliacao_media": 4.4,
        "avaliacoes_total": 180,
    },
    manual_title="Manual PC Gamer Vortex X3",
)

PC_X5 = CatalogProduct(
    sku="PC-VX5-BIV",
    name="PC Gamer Vortex X5",
    category="Computadores",
    subcategory="PCs Gamer",
    brand="Vortex",
    price=Decimal("4499.00"),
    stock_quantity=5,
    voltage="BIVOLT",
    power_watts=650,
    tier_rank=2,
    image_url="/images/pc-vx5-biv.svg",
    checkout_url="https://example.com/pc-vx5",
    specs_json={
        "placa_de_video": "RTX 4060 8 GB",
        "memoria_ram_gb": 16,
        "garantia_meses": 12,
        "avaliacao_media": 4.6,
        "avaliacoes_total": 312,
    },
    manual_title="Manual PC Gamer Vortex X5",
)

PC_X5P = CatalogProduct(
    sku="PC-VX5P-220V",
    name="PC Gamer Vortex X5 Pro",
    category="Computadores",
    subcategory="PCs Gamer",
    brand="Vortex",
    price=Decimal("5799.00"),
    stock_quantity=3,
    voltage="220V",
    power_watts=750,
    tier_rank=3,
    image_url="/images/pc-vx5p-220v.svg",
    checkout_url="https://example.com/pc-vx5p",
    specs_json={
        "placa_de_video": "RTX 4060 Ti",
        "memoria_ram_gb": 32,
        "garantia_meses": 24,
        "avaliacao_media": 4.7,
        "avaliacoes_total": 95,
    },
    manual_title="Manual PC Gamer Vortex X5 Pro",
)

NB_17_OUT = CatalogProduct(
    sku="NB-NX17-BIV",
    name="Notebook Gamer Nimbus 17 Pro",
    category="Computadores",
    subcategory="Notebooks Gamer",
    brand="Nimbus",
    price=Decimal("7199.00"),
    stock_quantity=0,
    voltage="BIVOLT",
    power_watts=280,
    tier_rank=3,
    image_url="/images/nb-nx17-biv.svg",
    checkout_url="https://example.com/nb-nx17",
    specs_json={
        "placa_de_video": "RTX 4070",
        "memoria_ram_gb": 32,
    },
    manual_title="Manual Notebook Gamer Nimbus 17 Pro",
)

WC_30 = CatalogProduct(
    sku="WC-1080-01",
    name="Webcam Cliqon View Full HD",
    category="Periféricos",
    subcategory="Webcams",
    brand="Cliqon",
    price=Decimal("189.90"),
    stock_quantity=17,
    voltage="N/A",
    tier_rank=1,
    image_url="/images/wc-1080-01.svg",
    checkout_url="https://example.com/wc-30",
    specs_json={"resolucao": "1920 x 1080", "fps": 30},
)

WC_60 = CatalogProduct(
    sku="WC-1080-60",
    name="Webcam Cliqon Stream 1080p60",
    category="Periféricos",
    subcategory="Webcams",
    brand="Cliqon",
    price=Decimal("249.90"),
    stock_quantity=14,
    voltage="N/A",
    tier_rank=2,
    image_url="/images/wc-1080-60.svg",
    checkout_url="https://example.com/wc-60",
    specs_json={"resolucao": "1920 x 1080", "fps": 60, "garantia_meses": 12, "avaliacao_media": 4.6, "avaliacoes_total": 520},
)

SF_180 = CatalogProduct(
    sku="SF-3L-180",
    name="Sofá Aurora 3 Lugares",
    category="Móveis",
    subcategory="Sofás",
    brand="Aurora",
    price=Decimal("1699.00"),
    stock_quantity=4,
    voltage="N/A",
    tier_rank=2,
    image_url="/images/sf-3l-180.svg",
    checkout_url="https://example.com/sf-180",
    specs_json={"largura_cm": 180, "profundidade_cm": 90, "altura_cm": 90, "lugares": 3},
)

SF_210 = CatalogProduct(
    sku="SF-3L-210R",
    name="Sofá Aurora 3 Lugares Retrátil",
    category="Móveis",
    subcategory="Sofás",
    brand="Aurora",
    price=Decimal("2199.00"),
    stock_quantity=3,
    voltage="N/A",
    tier_rank=3,
    image_url="/images/sf-3l-210r.svg",
    checkout_url="https://example.com/sf-210",
    specs_json={"largura_cm": 210, "profundidade_cm": 95, "altura_cm": 92, "lugares": 3},
)


def _assert_option_cards(cards: tuple[dict[str, object], ...], expected_skus: list[str]) -> None:
    assert [card["sku"] for card in cards] == expected_skus
    for card in cards:
        assert card["recommendation_type"] == "OPTION"
        assert card["badge_label"] == "Opção"
        assert int(str(card["stock_quantity"])) > 0


def test_ut_cu_09_discovery_answer_templates() -> None:
    # 1. With game not on PC (T3: PCs Gamer + GTA 6 carried slot)
    kb_chunk = _chunk("KB-GTA6-PLATAFORMAS", "GTA 6 plataformas e versão para PC", 1)
    slots = Slots(
        category=CategoryTarget("Computadores", ("PCs Gamer",)),
        game="GTA 6",
    )
    ans = discovery_answer(
        [PC_X3, PC_X5],
        slots,
        game_rows={},
        game_fact=KbFactHit(KB_GTA6_NO_PC.text, kb_chunk),
        relaxed=None,
        categories_in_stock=(),
    )
    assert ans.intent == "PURCHASE_INTENT"
    assert ans.sentences == (
        "Encontrei 2 opções em estoque em PCs Gamer, do menor para o maior preço:\n",
        "- SKU PC-VX3-BIV: PC Gamer Vortex X3, R$ 3.499,00, RTX 3050 6 GB, 16 GB de RAM, voltagem bivolt.\n",
        "- SKU PC-VX5-BIV: PC Gamer Vortex X5, R$ 4.499,00, RTX 4060 8 GB, 16 GB de RAM, voltagem bivolt.\n",
        f"Lembrando: {KB_GTA6_NO_PC.text} [Fonte: GTA 6 plataformas e versão para PC, p. 1].\n",
        "Para refinar, me diga o uso principal e o orçamento máximo.\n",
    )
    assert ans.cited == (kb_chunk,)
    _assert_option_cards(ans.cards, ["PC-VX3-BIV", "PC-VX5-BIV"])

    # 2. With PC game rows, budget, voltage and N/A voltage omission
    m_chunk = _chunk("PC-VX3-BIV", "Manual PC Gamer Vortex X3", 4)
    row = GameRow("Roblox", "1080p", "Alto", 160, m_chunk)
    slots_roblox = Slots(
        category=CategoryTarget("Computadores", ("PCs Gamer",)),
        budget_max=Decimal("5000"),
        voltage="127V",
        game="Roblox",
    )
    ans_game = discovery_answer(
        [PC_X3, PC_X5],
        slots_roblox,
        game_rows={"PC-VX3-BIV": row, "PC-VX5-BIV": None},
        game_fact=None,
        relaxed=None,
        categories_in_stock=(),
    )
    assert ans_game.sentences == (
        "Encontrei 2 opções em estoque em PCs Gamer até R$ 5.000,00 que funcionam em 127V, do menor para o maior preço:\n",
        "- SKU PC-VX3-BIV: PC Gamer Vortex X3, R$ 3.499,00, RTX 3050 6 GB, 16 GB de RAM, voltagem bivolt.\n",
        "  Roblox: 160 fps em 1080p, predefinição Alto [Fonte: Manual PC Gamer Vortex X3, p. 4].\n",
        "- SKU PC-VX5-BIV: PC Gamer Vortex X5, R$ 4.499,00, RTX 4060 8 GB, 16 GB de RAM, voltagem bivolt.\n",
        "  Roblox: desempenho não informado no manual.\n",
    )

    # 3. Empty search with budget relaxation
    ans_empty = discovery_answer(
        [],
        Slots(category=CategoryTarget("Computadores", ("PCs Gamer",)), budget_max=Decimal("2000")),
        game_rows={},
        game_fact=None,
        relaxed=PC_X3,
        categories_in_stock=(),
    )
    assert ans_empty.sentences == (
        "Não encontrei PCs Gamer em estoque até R$ 2.000,00.\n",
        "Sem o limite de orçamento, a opção mais barata em estoque é SKU PC-VX3-BIV: PC Gamer Vortex X3, R$ 3.499,00.\n",
    )
    assert ans_empty.cards == ()

    # 4. No category
    ans_nocat = discovery_answer(
        [],
        Slots(),
        game_rows={},
        game_fact=None,
        relaxed=None,
        categories_in_stock=[("Computadores", "PCs Gamer"), ("Móveis", "Sofás")],
    )
    assert ans_nocat.sentences == (
        "Posso ajudar com estas categorias em estoque: Computadores, Móveis. Qual delas você procura?\n",
    )


def test_ut_cu_10_game_fit_answer_templates() -> None:
    # 1. GTA 6 platform facts + no consoles
    kb_p = _chunk("KB-GTA6-PLATAFORMAS", "GTA 6 plataformas e versão para PC", 1)
    ans_gta6 = game_fit_answer(
        targets=[PC_X3],
        game="GTA 6",
        rows={},
        platform=[
            KbFactHit(KB_GTA6_PLATFORMS.text, kb_p),
            KbFactHit(KB_GTA6_NO_PC.text, kb_p),
        ],
        alias=None,
        alternative=None,
        consoles_in_catalog=False,
    )
    assert ans_gta6.sentences == (
        f"{KB_GTA6_PLATFORMS.text} [Fonte: GTA 6 plataformas e versão para PC, p. 1].\n",
        f"{KB_GTA6_NO_PC.text} [Fonte: GTA 6 plataformas e versão para PC, p. 1].\n",
        "Por isso, nenhum computador do catálogo roda GTA 6 hoje.\n",
        "O catálogo ativo não tem consoles.\n",
        "Se quiser, mostro o desempenho informado nos manuais em outros jogos, como GTA V e Roblox.\n",
    )
    assert ans_gta6.cards == ()
    assert ans_gta6.cited == (kb_p,)

    # 2. GTA RP alias -> GTA V row
    rp_chunk = _chunk("KB-GTA-RP", "GTA RP no PC", 1)
    m_chunk = _chunk("PC-VX3-BIV", "Manual PC Gamer Vortex X3", 4)
    gtav_row = GameRow("GTA V", "1080p", "Muito alto", 75, m_chunk)
    ans_rp = game_fit_answer(
        targets=[PC_X3],
        game="GTA RP",
        rows={"PC-VX3-BIV": gtav_row},
        platform=(),
        alias=KbFactHit(KB_GTA_RP.text, rp_chunk),
        alternative=None,
        consoles_in_catalog=False,
    )
    assert ans_rp.sentences == (
        f"{KB_GTA_RP.text} [Fonte: GTA RP no PC, p. 1].\n",
        "SKU PC-VX3-BIV: o manual informa 75 fps em GTA V a 1080p, predefinição Muito alto [Fonte: Manual PC Gamer Vortex X3, p. 4].\n",
        "O benchmark é de GTA V. O desempenho em servidores de GTA RP não foi medido nas fontes consultadas.\n",
        f"{GAME_FIT_GENERAL_INFO}\n",
    )
    assert ans_rp.cited == (rp_chunk, m_chunk)

    # 3. Single target missing row + alternative with OPTION card
    m5_chunk = _chunk("PC-VX5-BIV", "Manual PC Gamer Vortex X5", 4)
    alt_row = GameRow("Roblox", "1080p", "Alto", 200, m5_chunk)
    ans_alt = game_fit_answer(
        targets=[PC_X3],
        game="Roblox",
        rows={"PC-VX3-BIV": None},
        platform=(),
        alias=None,
        alternative=(PC_X5, alt_row),
        consoles_in_catalog=False,
    )
    assert ans_alt.sentences == (
        "SKU PC-VX3-BIV: o manual não informa desempenho em Roblox, então não confirmo que roda.\n",
        "Este outro tem desempenho informado em Roblox: SKU PC-VX5-BIV: 200 fps a 1080p, predefinição Alto [Fonte: Manual PC Gamer Vortex X5, p. 4].\n",
        f"{GAME_FIT_GENERAL_INFO}\n",
    )
    _assert_option_cards(ans_alt.cards, ["PC-VX5-BIV"])


def test_ut_cu_11_stream_fit_answer_templates() -> None:
    tw_chunk = _chunk("KB-TWITCH-TRANSMISSAO", "Twitch qualidade de transmissão", 1)
    h = KbMeasure(Decimal("1080"), "px", tw_chunk)
    f = KbMeasure(Decimal("60"), "fps", tw_chunk)

    # 1. Target 30 fps < 60 fps -> alternative WC-1080-60
    ans_fail = stream_fit_answer(WC_30, h, f, [WC_60])
    assert ans_fail.sentences == (
        "A Twitch recomenda transmitir em até 1080p a 60 fps [Fonte: Twitch qualidade de transmissão, p. 1].\n",
        "SKU WC-1080-01: resolução 1920 x 1080 a 30 fps, segundo a ficha técnica.\n",
        "Esta câmera não atende à qualidade máxima recomendada pela Twitch: fica em 30 fps, abaixo de 60 fps.\n",
        "Este outro atende: SKU WC-1080-60: resolução 1920 x 1080 a 60 fps, R$ 249,90.\n",
        f"{STREAM_FIT_GENERAL_INFO}\n",
    )
    _assert_option_cards(ans_fail.cards, ["WC-1080-60"])

    # 2. Target meets recommendation
    ans_ok = stream_fit_answer(WC_60, h, f, [WC_60])
    assert "Esta câmera atende à qualidade máxima recomendada pela Twitch.\n" in ans_ok.sentences
    assert ans_ok.cards == ()

    # 3. No target (catalog mode)
    ans_cat = stream_fit_answer(None, h, f, [WC_60])
    assert ans_cat.sentences == (
        "A Twitch recomenda transmitir em até 1080p a 60 fps [Fonte: Twitch qualidade de transmissão, p. 1].\n",
        "- SKU WC-1080-60: Webcam Cliqon Stream 1080p60, R$ 249,90, resolução 1920 x 1080 a 60 fps.\n",
        f"{STREAM_FIT_GENERAL_INFO}\n",
    )
    _assert_option_cards(ans_cat.cards, ["WC-1080-60"])


def test_ut_cu_12_dimension_fit_answer_templates() -> None:
    sf_chunk = _chunk("KB-SOFA-ESPACO", "Sofá espaço necessário no ambiente", 1)
    clearance = KbMeasure(Decimal("10"), "cm", sf_chunk)

    # 1. No measure -> prompt for width
    ans_ask = dimension_fit_answer(SF_210, None, clearance, [SF_180, SF_210])
    assert ans_ask.sentences == (
        "Qual é a largura livre do espaço onde o sofá vai ficar, em metros ou centímetros?\n",
    )
    assert ans_ask.cards == ()

    # 2. Target 210 cm in 200 cm room -> doesn't fit, offers SF-3L-180
    ans_no = dimension_fit_answer(SF_210, Decimal("200"), clearance, [SF_180, SF_210])
    assert ans_no.sentences == (
        "SKU SF-3L-210R: largura de 210 cm, profundidade de 95 cm.\n",
        "A orientação é deixar pelo menos 10 cm livres de cada lado do sofá [Fonte: Sofá espaço necessário no ambiente, p. 1], então ele precisa de 230 cm.\n",
        "Não cabe nos 200 cm informados.\n",
        "Este outro cabe com folga: SKU SF-3L-180: largura de 180 cm, 3 lugares, R$ 1.699,00.\n",
        f"{DIMENSION_FIT_GENERAL_INFO}\n",
    )
    _assert_option_cards(ans_no.cards, ["SF-3L-180"])

    # 3. Target 180 cm in 190 cm room -> fits without clearance
    ans_tight = dimension_fit_answer(SF_180, Decimal("190"), clearance, [SF_180])
    assert "Cabe nos 190 cm informados, mas sem a folga recomendada.\n" in ans_tight.sentences

    # 4. Target 180 cm in 200 cm room -> fits with clearance
    ans_fit = dimension_fit_answer(SF_180, Decimal("200"), clearance, [SF_180])
    assert "Cabe nos 200 cm informados, com a folga recomendada.\n" in ans_fit.sentences


def test_ut_cu_13_set_voltage_answer_templates() -> None:
    ans = set_voltage_answer([PC_X3, PC_X5, PC_X5P, NB_17_OUT, WC_60], "127V")
    assert ans.intent == "PRODUCT_COMPARISON"
    assert ans.sentences == (
        "Não: 3 dos 5 produtos mostrados funcionam em 127V.\n",
        "- SKU PC-VX3-BIV: bivolt, funciona em 127V.\n",
        "- SKU PC-VX5-BIV: bivolt, funciona em 127V.\n",
        "- SKU PC-VX5P-220V: 220V, não deve ser ligado em 127V.\n",
        "- SKU NB-NX17-BIV: bivolt, funciona em 127V (esgotado no momento).\n",
        "- SKU WC-1080-60: não é ligado diretamente na tomada.\n",
    )
    # Sold-out NB-NX17-BIV and unpowered WC-1080-60 do not get compatible voltage cards
    _assert_option_cards(ans.cards, ["PC-VX3-BIV", "PC-VX5-BIV"])

    ans_all = set_voltage_answer([PC_X3, PC_X5], "127V")
    assert ans_all.sentences[0] == "Sim: os 2 produtos mostrados funcionam em 127V.\n"

    ans_none = set_voltage_answer([PC_X5P], "127V")
    assert ans_none.sentences[0] == "Não: nenhum dos 1 produtos mostrados funciona em 127V.\n"


def test_ut_cu_14_price_rank_answer_templates() -> None:
    # 1. Referent is not cheapest, from_peers=True
    ans_peer = price_rank_answer([PC_X3, PC_X5, PC_X5P], referent=PC_X5, direction="cheapest", from_peers=True)
    assert ans_peer.sentences == (
        "Comparando com PCs Gamer em estoque: Não. Este produto aqui é mais barato: SKU PC-VX3-BIV, por R$ 3.499,00, contra R$ 4.499,00 do SKU PC-VX5-BIV.\n",
    )
    _assert_option_cards(ans_peer.cards, ["PC-VX3-BIV"])

    # 2. Referent is cheapest
    ans_yes = price_rank_answer([PC_X3, PC_X5], referent=PC_X3, direction="cheapest", from_peers=False)
    assert ans_yes.sentences == (
        "Sim: SKU PC-VX3-BIV é o mais barato dos 2 comparados, por R$ 3.499,00.\n",
    )

    # 3. No referent
    ans_noref = price_rank_answer([PC_X3, PC_X5], referent=None, direction="cheapest", from_peers=False)
    assert ans_noref.sentences == (
        "O mais barato dos 2 comparados é SKU PC-VX3-BIV, por R$ 3.499,00; o mais caro é SKU PC-VX5-BIV, por R$ 4.499,00.\n",
    )

    # 4. Tie
    pc_tie = PC_X5.model_copy(update={"price": Decimal("3499.00")})
    ans_tie = price_rank_answer([PC_X3, pc_tie], referent=None, direction="cheapest", from_peers=False)
    assert ans_tie.sentences == (
        "SKU PC-VX3-BIV e SKU PC-VX5-BIV empatam no menor preço, R$ 3.499,00.\n",
    )


def test_ut_cu_15_comparison_answer_templates() -> None:
    m3 = _chunk("PC-VX3-BIV", "Manual PC Gamer Vortex X3", 4)
    m5 = _chunk("PC-VX5-BIV", "Manual PC Gamer Vortex X5", 4)
    rows = {
        "PC-VX3-BIV": GameRow("Roblox", "1080p", "Alto", 160, m3),
        "PC-VX5-BIV": GameRow("Roblox", "1080p", "Alto", 210, m5),
        "NB-NX17-BIV": None,
    }
    ans = comparison_answer([PC_X3, PC_X5, NB_17_OUT], rows, "Roblox")
    assert ans.sentences == (
        "Não há um melhor absoluto; comparo pelos dados do catálogo:\n",
        "- SKU PC-VX3-BIV: R$ 3.499,00, RTX 3050 6 GB, 16 GB de RAM, voltagem bivolt, garantia de 12 meses, avaliação 4,4 de 5 em 180 avaliações.\n",
        "- SKU PC-VX5-BIV: R$ 4.499,00, RTX 4060 8 GB, 16 GB de RAM, voltagem bivolt, garantia de 12 meses, avaliação 4,6 de 5 em 312 avaliações.\n",
        "- SKU NB-NX17-BIV: R$ 7.199,00, RTX 4070, 32 GB de RAM, voltagem bivolt, garantia não informada, sem avaliações no catálogo (esgotado no momento).\n",
        "Menor preço: SKU PC-VX3-BIV.\n",
        "Maior garantia: SKU PC-VX3-BIV e SKU PC-VX5-BIV, 12 meses.\n",
        "Melhor avaliação média: SKU PC-VX5-BIV, 4,6 de 5.\n",
        "Maior desempenho informado em Roblox: SKU PC-VX5-BIV, 210 fps [Fonte: Manual PC Gamer Vortex X5, p. 4].\n",
        "Se me disser o que pesa mais para você, preço, garantia ou desempenho, indico um deles.\n",
    )
    assert ans.cited == (m5,)
    _assert_option_cards(ans.cards, ["PC-VX3-BIV", "PC-VX5-BIV"])


def test_ut_cu_16_brand_opinion_answer_and_fixed_messages() -> None:
    ans = brand_opinion_answer([PC_X3, NB_17_OUT])
    assert ans.sentences == (
        "Não tenho dados de confiabilidade ou de defeitos por marca, então não faço ranking de marcas.\n",
        "Os critérios objetivos do catálogo para os produtos mostrados são garantia e avaliações:\n",
        "- SKU PC-VX3-BIV, marca Vortex: garantia de 12 meses, avaliação 4,4 de 5 em 180 avaliações.\n",
        "- SKU NB-NX17-BIV, marca Nimbus: garantia não informada, sem avaliações no catálogo (esgotado no momento).\n",
    )
    assert ans.cards == ()
    assert ans.cited == ()
    assert GREETING_MESSAGE.startswith("Olá! Posso ajudar")
    assert clarify_product_message("PC-VX3-BIV") == (
        "Sobre qual dos produtos mostrados? Cite o SKU, por exemplo SKU PC-VX3-BIV, ou abra a página do produto.\n"
    )
