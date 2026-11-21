"""UT-CU-01..06: pure slot extraction, length normalization and conversation state."""

from decimal import Decimal

import pytest
from app.consultant.conversation import (
    CategoryTarget,
    ConversationState,
    Slots,
    conversation_state,
    merge_slots,
)
from app.consultant.slots import (
    parse_budget,
    parse_category,
    parse_game,
    parse_seats,
    parse_skus,
    parse_slots,
    parse_voltage,
)
from app.guardrails.output import length_measures_cm
from app.models.schemas import ChatTurn, ConsultantRequest


@pytest.mark.parametrize(
    "text,expected",
    [
        ("quero um computador novo", CategoryTarget("Computadores", ("PCs Gamer", "Notebooks Gamer"))),
        ("mas quero um PC", CategoryTarget("Computadores", ("PCs Gamer",))),
        ("procuro um desktop gamer", CategoryTarget("Computadores", ("PCs Gamer",))),
        ("qual notebook funciona em 127V?", CategoryTarget("Computadores", ("Notebooks Gamer",))),
        ("quero um monitor para jogos", CategoryTarget("Monitores", ("Monitores Gamer",))),
        ("preciso de uma câmera para live", CategoryTarget("Periféricos", ("Webcams",))),
        ("qual webcam serve para Twitch?", CategoryTarget("Periféricos", ("Webcams",))),
        ("esse sofá cabe na sala?", CategoryTarget("Móveis", ("Sofás",))),
        ("quero uma airfryer", CategoryTarget("Eletroportáteis", ("Fritadeiras Elétricas",))),
        ("procuro uma cafeteira", CategoryTarget("Eletroportáteis", ("Cafeteiras",))),
        ("me conta uma piada", None),
    ],
)
def test_ut_cu_01_category_table(text: str, expected: CategoryTarget | None) -> None:
    assert parse_category(text) == expected


@pytest.mark.parametrize(
    "text,expected",
    [
        ("até 3 mil", Decimal("3000")),
        ("até R$ 4.500", Decimal("4500")),
        ("no máximo 5000 reais", Decimal("5000")),
        ("orçamento de 3.500,00", Decimal("3500")),
        ("posso gastar até 2.500", Decimal("2500")),
        ("3 mil reais", Decimal("3000")),
        ("R$ 4.499", None),
        ("custa R$ 4.499,00", None),
    ],
)
def test_ut_cu_02_budget_extraction(text: str, expected: Decimal | None) -> None:
    assert parse_budget(text) == expected


@pytest.mark.parametrize(
    "text,expected",
    [
        ("posso ligar em 127V?", "127V"),
        ("minha tomada é 110", "127V"),
        ("tomada de 127", "127V"),
        ("funciona em 110v?", "127V"),
        ("preciso de 220V", "220V"),
        ("tomada 220", "220V"),
        ("220 reais", None),
        ("modelo 1100", None),
    ],
)
def test_ut_cu_03_voltage_extraction(text: str, expected: str | None) -> None:
    assert parse_voltage(text) == expected


@pytest.mark.parametrize(
    "text,expected",
    [
        ("pra jogar GTA 6", "GTA 6"),
        ("roda GTA VI?", "GTA 6"),
        ("quero jogar gta6", "GTA 6"),
        ("e GTA RP?", "GTA RP"),
        ("funciona com gta roleplay?", "GTA RP"),
        ("roda GTA 5?", "GTA V"),
        ("consigo jogar GTA V?", "GTA V"),
        ("consigo jogar Roblox nesse computador?", "Roblox"),
        ("roda Fortnite?", "Fortnite"),
        ("quero jogar CS2", "Counter-Strike 2"),
        ("quero um sofá", None),
    ],
)
def test_ut_cu_04_game_extraction(text: str, expected: str | None) -> None:
    assert parse_game(text) == expected


@pytest.mark.parametrize(
    "text,expected",
    [
        ("2 metros", [Decimal("200")]),
        ("200 cm", [Decimal("200")]),
        ("2,5 m", [Decimal("250")]),
        ("1.80 m", [Decimal("180")]),
        ("180 centímetros", [Decimal("180")]),
        ("dois metros", []),
        ("R$ 2.000", []),
    ],
)
def test_ut_cu_05_length_measures_cm(text: str, expected: list[Decimal]) -> None:
    assert length_measures_cm(text) == expected


def test_ut_cu_06_merge_slots_latest_wins_and_resets_on_category_change() -> None:
    # Same macro-category ("Computadores" -> "PCs Gamer") preserves the GTA 6 game slot and budget.
    kept = merge_slots(
        [
            "quero um computador novo até 6 mil",
            "pra jogar GTA 6",
            "mas quero um PC",
        ]
    )
    assert kept.category == CategoryTarget("Computadores", ("PCs Gamer",))
    assert kept.game == "GTA 6"
    assert kept.budget_max == Decimal("6000")

    # Latest value in the same category wins; room_width_cm is taken from current message only.
    updated = merge_slots(
        [
            "quero um sofá de 2 lugares, tenho 2 metros",
            "prefiro de 3 lugares até R$ 2.000",
        ]
    )
    assert updated.category == CategoryTarget("Móveis", ("Sofás",))
    assert updated.seats == 3
    assert updated.budget_max == Decimal("2000")
    assert updated.room_width_cm is None

    # Switching from Computadores to Móveis stops the merge and drops the stale computer budget/game.
    reset = merge_slots(
        [
            "quero um computador até 5 mil pra jogar Roblox em 127V",
            "agora quero um sofá de 3 lugares",
        ]
    )
    assert reset.category == CategoryTarget("Móveis", ("Sofás",))
    assert reset.budget_max is None
    assert reset.game is None
    assert reset.voltage is None
    assert reset.seats == 3


def test_ut_cu_06_conversation_state_filters_override_and_last_shown_set_wins() -> None:
    request = ConsultantRequest(
        sku=None,
        question="Compare SKU PC-VX3-BIV e SKU PC-VX5-BIV em 2 metros",
        history=[
            ChatTurn(role="user", content="quero um computador até 4 mil em 220V"),
            ChatTurn(
                role="assistant",
                content="Encontrei 2 opções:",
                recommended_skus=["PC-VX3-BIV", "NB-NX15-BIV"],
            ),
            ChatTurn(role="user", content="mas quero um PC"),
            ChatTurn(
                role="assistant",
                content="Encontrei 4 opções:",
                recommended_skus=["PC-VX3-BIV", "PC-VX5-BIV", "PC-VX5P-220V", "PC-VX7-220V"],
            ),
            ChatTurn(role="user", content="qual a marca mais confiável?"),
            ChatTurn(role="assistant", content="Não tenho dados de confiabilidade..."),
        ],
        preferred_voltage="127V",
        budget_max=Decimal("5500.00"),
    )
    state: ConversationState = conversation_state(request)
    assert state.current_sku is None
    assert state.shown_skus == ("PC-VX3-BIV", "PC-VX5-BIV", "PC-VX5P-220V", "PC-VX7-220V")
    assert state.mentioned_skus == ("PC-VX3-BIV", "PC-VX5-BIV")
    assert state.slots == Slots(
        category=CategoryTarget("Computadores", ("PCs Gamer",)),
        budget_max=Decimal("5500.00"),
        voltage="127V",
        game=None,
        seats=None,
        room_width_cm=Decimal("200"),
    )
    assert parse_seats("sofá de 3 lugares") == 3
    assert parse_skus("Veja PC-VX3-BIV e WC-1080-60") == ("PC-VX3-BIV", "WC-1080-60")
    assert parse_slots("sofá 3 lugares em 2 metros").room_width_cm == Decimal("200")
